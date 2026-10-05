const test = require('node:test');
const assert = require('node:assert/strict');
const {localPair, validateRemotePair} = require('../ai_interior_designer.js');

const config = {
  axis_order: ['layout', 'palette'],
  opening_pair: ['side_quiet', 'window_dark'],
  variants: [
    {key:'side_quiet', label:'Side quiet', axes:{layout:'side', palette:'quiet'}},
    {key:'window_quiet', label:'Window quiet', axes:{layout:'window', palette:'quiet'}},
    {key:'side_dark', label:'Side dark', axes:{layout:'side', palette:'dark'}},
    {key:'window_dark', label:'Window dark', axes:{layout:'window', palette:'dark'}}
  ]
};

test('opening pair follows the declared first A/B comparison', () => {
  const pair = localPair(config, []);
  assert.deepEqual(pair.candidates.map(x => x.key), ['side_quiet', 'window_dark']);
});

test('next local pair keeps the winner and prefers an untested isolated axis', () => {
  const history = [{winner_key:'side_quiet', loser_key:'window_dark', comparison_axis:'layout'}];
  const pair = localPair(config, history);
  assert.equal(pair.candidates[0].key, 'side_quiet');
  assert.notEqual(pair.candidates[1].key, 'window_dark');
  assert.ok(['window_quiet', 'side_dark'].includes(pair.candidates[1].key));
});

test('remote output is accepted only for two whitelisted distinct candidates', () => {
  assert.deepEqual(
    validateRemotePair(config, {candidate_a:'side_quiet', candidate_b:'side_dark', comparison_axis:'palette'}).candidates.map(x => x.key),
    ['side_quiet', 'side_dark']
  );
  assert.equal(validateRemotePair(config, {candidate_a:'side_quiet', candidate_b:'made_up', comparison_axis:'palette'}), null);
  assert.equal(validateRemotePair(config, {candidate_a:'side_quiet', candidate_b:'side_quiet', comparison_axis:'palette'}), null);
});
