# AI Designer Worker

Mały backend dla trybu A/B w portalu. Nie przechowuje geometrii ani klucza API w przeglądarce.
Model AI wybiera wyłącznie spośród wariantów 3D, które wcześniej przeszły walidację projektu.

## Cloudflare Workers

1. Utwórz Worker i wgraj \`worker.js\`.
2. Dodaj sekret \`OPENAI_API_KEY\`.
3. Opcjonalnie ustaw \`OPENAI_MODEL\` (domyślnie \`gpt-6-luna\`).
4. Ustaw \`ALLOWED_ORIGIN=https://rutkala.github.io\`.
5. W \`modules/06_interior/extracts/office.yaml\` wpisz publiczny adres endpointu do \`design_variants.backend_endpoint\`.

Bez endpointu portal nadal działa w szybkim trybie lokalnym: pokazuje i iteruje po zwalidowanych wariantach A/B, ale pary dobiera algorytm deterministyczny zamiast modelu AI.

Backend nie przyjmuje dowolnej geometrii od modelu. Żądanie zawiera listę dopuszczonych kluczy wariantów, osie porównania i historię wyborów. Odpowiedź modelu jest walidowana przez JSON Schema i ponownie sprawdzana po stronie Workera.
