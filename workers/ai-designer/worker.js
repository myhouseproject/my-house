const json = (body, status = 200, origin = '*') => new Response(JSON.stringify(body), {
  status,
  headers: {
    'content-type': 'application/json; charset=utf-8',
    'access-control-allow-origin': origin,
    'access-control-allow-methods': 'POST,OPTIONS',
    'access-control-allow-headers': 'content-type',
    'cache-control': 'no-store'
  }
});

function allowedOrigin(request, env) {
  const requestOrigin = request.headers.get('origin') || '';
  const configured = String(env.ALLOWED_ORIGIN || '').trim();
  if (!configured) return requestOrigin || '*';
  return requestOrigin === configured ? configured : null;
}

function fallbackPair(payload) {
  const variants = Array.isArray(payload?.variants) ? payload.variants : [];
  if (variants.length < 2) throw new Error('At least two variants are required');
  const history = Array.isArray(payload?.history) ? payload.history : [];
  const lastWinner = String(history.at(-1)?.winner_key || variants[0].key);
  const first = variants.find(v => String(v.key) === lastWinner) || variants[0];
  const compared = new Set(history.map(h => [String(h.winner_key), String(h.loser_key)].sort().join('|')));
  const axes = Array.isArray(payload.axis_order) ? payload.axis_order : [];
  const score = variant => {
    const key = String(variant.key);
    if (key === String(first.key)) return -Infinity;
    const pair = [key, String(first.key)].sort().join('|');
    let s = compared.has(pair) ? 0 : 100;
    const diffs = axes.filter(axis => String(first.axes?.[axis] ?? '') !== String(variant.axes?.[axis] ?? ''));
    if (diffs.length === 1) s += 30;
    if (diffs.includes(axes[history.length % Math.max(axes.length, 1)])) s += 20;
    return s - Math.max(0, diffs.length - 1) * 5;
  };
  const second = variants.filter(v => String(v.key) !== String(first.key)).sort((a,b) => score(b) - score(a))[0];
  const comparisonAxis = axes.find(axis => String(first.axes?.[axis] ?? '') !== String(second.axes?.[axis] ?? '')) || 'kierunek';
  return {candidate_a:first.key, candidate_b:second.key, comparison_axis:comparisonAxis, source:'fallback'};
}

function extractOutputText(response) {
  if (typeof response?.output_text === 'string' && response.output_text) return response.output_text;
  for (const item of response?.output || []) {
    if (item?.type !== 'message') continue;
    for (const content of item.content || []) {
      if (content?.type === 'output_text' && typeof content.text === 'string') return content.text;
    }
  }
  throw new Error('Model response did not contain output text');
}

function validatePayload(payload) {
  if (!payload || payload.schema_version !== 1) throw new Error('Unsupported payload');
  if (!Array.isArray(payload.variants) || payload.variants.length < 2 || payload.variants.length > 40) throw new Error('Invalid variants');
  const seen = new Set();
  for (const variant of payload.variants) {
    const key = String(variant?.key || '');
    if (!key || key.length > 80 || seen.has(key)) throw new Error('Invalid variant key');
    seen.add(key);
  }
  if (Array.isArray(payload.history) && payload.history.length > 50) throw new Error('History too long');
  return payload;
}

async function askOpenAI(payload, env) {
  if (!env.OPENAI_API_KEY) return fallbackPair(payload);
  const allowed = new Set(payload.variants.map(v => String(v.key)));
  const schema = {
    type: 'object',
    additionalProperties: false,
    required: ['candidate_a', 'candidate_b', 'comparison_axis'],
    properties: {
      candidate_a: {type:'string', enum:[...allowed]},
      candidate_b: {type:'string', enum:[...allowed]},
      comparison_axis: {type:'string'}
    }
  };
  const system = [
    'You are the selection engine for an adaptive A/B interior-design tournament.',
    'The architecture is immutable. You are NOT allowed to invent furniture coordinates or geometry.',
    'Choose only from the supplied validated variant keys.',
    'The goal is to learn the couple’s preferences efficiently.',
    'Keep the previous winner when useful and choose a challenger that isolates one meaningful axis when possible.',
    'Avoid repeating the same pair unless all informative alternatives have already been compared.',
    'Return exactly two distinct candidate keys.'
  ].join(' ');
  const response = await fetch('https://api.openai.com/v1/responses', {
    method: 'POST',
    headers: {
      'authorization': 'Bearer ' + env.OPENAI_API_KEY,
      'content-type': 'application/json'
    },
    body: JSON.stringify({
      model: env.OPENAI_MODEL || 'gpt-6-luna',
      store: false,
      max_output_tokens: 220,
      input: [
        {role:'developer', content:[{type:'input_text', text:system}]},
        {role:'user', content:[{type:'input_text', text:JSON.stringify(payload)}]}
      ],
      text: {format:{type:'json_schema', name:'design_pair', strict:true, schema}}
    })
  });
  if (!response.ok) throw new Error('OpenAI HTTP ' + response.status + ': ' + (await response.text()).slice(0, 500));
  const data = await response.json();
  const result = JSON.parse(extractOutputText(data));
  if (!allowed.has(String(result.candidate_a)) || !allowed.has(String(result.candidate_b)) || result.candidate_a === result.candidate_b)
    throw new Error('Model selected invalid candidates');
  return {...result, source:'openai'};
}

export default {
  async fetch(request, env) {
    const origin = allowedOrigin(request, env);
    if (!origin) return json({error:'Origin not allowed'}, 403, 'null');
    if (request.method === 'OPTIONS') return new Response(null, {
      status: 204,
      headers: {
        'access-control-allow-origin': origin,
        'access-control-allow-methods': 'POST,OPTIONS',
        'access-control-allow-headers': 'content-type',
        'access-control-max-age': '86400'
      }
    });
    if (request.method !== 'POST') return json({error:'POST required'}, 405, origin);
    try {
      const payload = validatePayload(await request.json());
      let result;
      try { result = await askOpenAI(payload, env); }
      catch (error) {
        result = fallbackPair(payload);
        result.warning = 'AI unavailable; deterministic fallback used';
      }
      return json(result, 200, origin);
    } catch (error) {
      return json({error:String(error?.message || error)}, 400, origin);
    }
  }
};
