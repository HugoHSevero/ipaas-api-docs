// Cadastro do TOTVS Assinatura Eletronica - TAE no iPaaS.
//
// Colar no console do DevTools com uma aba de https://ipaas.totvs.app logada.
// O token sai do cookie jwt.token da própria página; nada é gravado em lugar nenhum.
//
// Rode primeiro com CRIAR = false: só lê (sessão, tenant, o que já existe) e não altera nada.
// Conferido o resultado, rode de novo com CRIAR = true. O script é idempotente:
// reaproveita app, ambiente e serviços com o mesmo nome e só cria o que falta.
// A conta NÃO é criada aqui (exige o token do TAE; cadastrar à parte).

(async () => {
  const CRIAR = false;
  const SHA = '8711c47d0d72a20415253c342b863092fa974270'; // URL por SHA evita o cache do raw.githubusercontent
  const REPO = `https://raw.githubusercontent.com/HugoHSevero/ipaas-api-docs/${SHA}/tae`;

  const APP = {
    name: 'TOTVS Assinatura Eletronica - TAE',
    description: 'Assinatura eletrônica de documentos: autenticação e usuários, upload e publicação de documentos, assinatura, contatos, webhooks e dead letter.',
  };
  const AMBIENTE = { name: 'Produção', baseURL: 'https://totvssign.totvs.app' };
  const API_KEY = 'e90e6f18-c1bb-4170-9d10-5e45be5314c6';
  const SERVICOS = [
    { name: 'Identidade', icon: 'user', arquivo: 'openapi-identidade.ipaas.json', ops: 28,
      description: 'API IdentityIntegration: login (token JWE), usuários, administradores, empresas, usuários de serviço e código de verificação' },
    { name: 'Documentos', icon: 'product', arquivo: 'openapi-documentos.ipaas.json', ops: 38,
      description: 'API Documents: upload de envelopes, publicações, pesquisas, download, anexos e pastas' },
    { name: 'Assinaturas', icon: 'light-bulb', arquivo: 'openapi-assinaturas.ipaas.json', ops: 31,
      description: 'API SignIntegration: assinar, rejeitar, destinatários e observadores, opções da publicação, callbacks e certificado em nuvem' },
    { name: 'Contatos', icon: 'user', arquivo: 'openapi-contatos.ipaas.json', ops: 23,
      description: 'API Contact: contatos e grupos de contatos do usuário' },
    { name: 'Webhooks', icon: 'adb', arquivo: 'openapi-webhooks.ipaas.json', ops: 7,
      description: 'API Webhooks: subscriptions, callbacks, eventos disponíveis e histórico de envio' },
    { name: 'Dead Letter', icon: 'adb', arquivo: 'openapi-deadletter.ipaas.json', ops: 4,
      description: 'API DeadLetter: pesquisa, consulta, exclusão e reprocessamento de webhooks que falharam' },
  ];

  const BASE = 'https://api-ipaas.totvs.app/ipaas/api';
  const m = document.cookie.match(/(?:^|;\s*)jwt\.token=([^;]+)/);
  if (!m) throw new Error('Cookie jwt.token não encontrado: faça login de novo nesta aba.');
  const headers = { authorization: 'Bearer ' + m[1], accept: 'application/json', 'content-type': 'application/json' };

  async function api(method, path, body) {
    const r = await fetch(BASE + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    const txt = await r.text();
    let data = null;
    try { data = txt ? JSON.parse(txt) : null; } catch { data = txt; }
    if (!r.ok) throw new Error(`${method} ${path} -> ${r.status}: ${txt.slice(0, 500)}`);
    return data;
  }
  const lista = (d) => Array.isArray(d) ? d : (d?.items ?? d?.content ?? d?.data ?? []);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const log = [];

  // 1. sessão
  await api('GET', '/v2/auth-models?page=1&pageSize=1');
  log.push(['sessão', 'ok (200)']);

  // 2. tenant e app existente
  const apps = lista(await api('GET', '/v3/applications?page=1&pageSize=9999'));
  const tenants = [...new Set(apps.filter((a) => a.isCustom).map((a) => a.ownerTenantName).filter(Boolean))];
  log.push(['tenant (ownerTenantName dos apps custom)', tenants.join(', ') || '(nenhum app custom)']);
  let app = apps.find((a) => a.name === APP.name);
  log.push(['app', app ? `já existe: ${app.componentId ?? app.id} (isCustom=${app.isCustom}, dono=${app.ownerTenantName})` : 'não existe']);
  if (app && !app.isCustom) throw new Error('Já existe um app com esse nome no catálogo TOTVS (isCustom=false). Parei sem alterar nada.');

  let appId = app && (app.componentId ?? app.id);
  let ambiente = null, servicos = [];
  if (appId) {
    const envs = lista(await api('GET', `/v2/environments/?applicationId=${appId}&expand=authModels&expand=accounts`));
    ambiente = envs.find((e) => e.name === AMBIENTE.name) || null;
    log.push(['ambientes existentes', envs.map((e) => `${e.name} -> ${e.baseURL}`).join(' | ') || '(nenhum)']);
    servicos = lista(await api('GET', `/v3/application-services?applicationId=${appId}&page=1&pageSize=500`));
    log.push(['serviços existentes', servicos.map((s) => s.name).join(', ') || '(nenhum)']);
  }

  if (!CRIAR) {
    console.table(log);
    console.log('Somente leitura. Confira acima e rode de novo com CRIAR = true.');
    return;
  }
  if (SHA.startsWith('COLOQUE')) throw new Error('Preencha SHA antes de importar.');

  // 3. app
  if (!appId) {
    const novo = await api('POST', '/v3/applications', APP);
    appId = novo.componentId; // o id vem em componentId, não em id
    log.push(['app criado', appId]);
  }

  // 4. ambiente (authModelIds, não authModels)
  if (!ambiente) {
    ambiente = await api('POST', '/v2/environments', {
      name: AMBIENTE.name, type: 'REST', baseURL: AMBIENTE.baseURL,
      applicationId: appId, authModelIds: [API_KEY], active: true,
    });
    log.push(['ambiente criado', `${ambiente.id} -> ${AMBIENTE.baseURL}`]);
  }
  const envId = ambiente.id;

  // 5. serviços + importação
  for (const s of SERVICOS) {
    let svc = servicos.find((x) => x.name === s.name);
    if (!svc) {
      svc = await api('POST', '/v3/application-services', {
        name: s.name, description: s.description, applicationId: appId,
        environmentId: envId, resourceType: 'REST', icon: s.icon,
      });
    }
    const svcId = svc.id ?? svc.componentId;
    const url = `${REPO}/${s.arquivo}`;
    await api('POST', '/v3/rest-resources/import-swagger', {
      applicationId: appId, serviceId: svcId, endPoint: url, swaggerEndPoint: url, update: true,
    });
    // importação é assíncrona: 200 não significa que terminou
    let n = 0;
    for (let i = 0; i < 40; i++) {
      await sleep(1500);
      n = lista(await api('GET', `/v3/rest-resources?serviceId=${svcId}&fields=id&fields=name&page=1&pageSize=9999`)).length;
      if (n >= s.ops) break;
    }
    log.push([`serviço ${s.name}`, `${svcId}: ${n}/${s.ops} recursos ${n === s.ops ? 'OK' : 'DIVERGENTE'}`]);
  }

  // 6. conferência do ambiente
  const envs = lista(await api('GET', `/v2/environments/?applicationId=${appId}&expand=authModels`));
  const env = envs.find((e) => e.id === envId);
  log.push(['ambiente (GET)', `${env?.baseURL} active=${env?.active} auth=${(env?.authModels || []).map((a) => a.type ?? a.name).join(',')}`]);

  console.table(log);
})();
