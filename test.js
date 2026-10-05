/**
 * test.js · Test suite for Snowgate Forum Node.js server with Captcha Gate
 */

const assert = require('assert');
const http = require('http');
const querystring = require('querystring');
const handler = require('./api/index.js');

const server = http.createServer((req, res) => {
  handler(req, res);
});

server.listen(0, '127.0.0.1', () => {
  const port = server.address().port;
  const baseUrl = `http://127.0.0.1:${port}`;
  const authHeaders = { 'X-Snowgate-Password': 'two rivers crossing.' };

  console.log(`[TEST] Testing Snowgate Forum on port ${port}...`);

  // Test 1: Unauthenticated GET / -> 401 Gate Challenge
  http.get(baseUrl + '/', resGate => {
    assert.strictEqual(resGate.statusCode, 401);
    let gateData = '';
    resGate.on('data', chunk => (gateData += chunk));
    resGate.on('end', () => {
      assert.ok(gateData.includes('say the password'), 'Must render challenge prompt: say the password');
      assert.ok(gateData.includes('SNOWGATE GATEWAY'), 'Must show gateway header');
      console.log('✓ Test 1: Unauthenticated request received 401 gate challenge ("say the password")');

      // Test 2: POST /gate with wrong password -> 401
      const reqBadPass = http.request(
        baseUrl + '/gate',
        { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
        resBadPass => {
          assert.strictEqual(resBadPass.statusCode, 401);
          console.log('✓ Test 2: Incorrect password rejected with 401');

          // Test 3: POST /gate with correct password -> 303 + Set-Cookie
          const reqGoodPass = http.request(
            baseUrl + '/gate',
            { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
            resGoodPass => {
              assert.strictEqual(resGoodPass.statusCode, 303);
              const cookie = resGoodPass.headers['set-cookie'];
              assert.ok(cookie && cookie[0].includes('snowgate_gate'), 'Must issue snowgate_gate cookie');
              console.log('✓ Test 3: Correct password "two rivers crossing." unlocked gate with 303 and Set-Cookie');

              // Test 4: Authenticated GET / (HTML Board Index)
              http.get(baseUrl + '/', { headers: authHeaders }, res => {
                assert.strictEqual(res.statusCode, 200);
                assert.ok(res.headers['content-type'].includes('text/html'));
                let data = '';
                res.on('data', chunk => (data += chunk));
                res.on('end', () => {
                  assert.ok(data.includes('SNOWGATE'), 'HTML must contain SNOWGATE brand');
                  assert.ok(data.includes('/tech/'), 'HTML must contain /tech/');
                  assert.ok(data.includes('--bg-primary: #0a0e17'), 'Must contain bluish dark mode background');
                  assert.ok(data.includes('svg'), 'Must contain Snowgate SVG emblem');
                  assert.ok(data.includes('class="greentext"'), 'Must support greentext');
                  console.log('✓ Test 4: Authenticated GET / HTML board index passed');

                  // Test 5: GET /?format=json
                  http.get(baseUrl + '/?format=json', { headers: authHeaders }, resJson => {
                    assert.strictEqual(resJson.statusCode, 200);
                    let jsonData = '';
                    resJson.on('data', chunk => (jsonData += chunk));
                    resJson.on('end', () => {
                      const posts = JSON.parse(jsonData);
                      assert.ok(Array.isArray(posts));
                      assert.ok(posts.length > 0);
                      console.log(`✓ Test 5: Authenticated GET /?format=json returned ${posts.length} posts`);

                      // Test 6: GET /catalog
                      http.get(baseUrl + '/catalog', { headers: authHeaders }, resCat => {
                        assert.strictEqual(resCat.statusCode, 200);
                        let catData = '';
                        resCat.on('data', chunk => (catData += chunk));
                        resCat.on('end', () => {
                          assert.ok(catData.includes('/tech/ - Catalog'));
                          console.log('✓ Test 6: Authenticated GET /catalog passed');

                          // Test 7: POST / with secret key -> 403 Forbidden
                          const reqBad = http.request(
                            baseUrl + '/',
                            {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json', ...authHeaders },
                            },
                            resBad => {
                              assert.strictEqual(resBad.statusCode, 403);
                              console.log('✓ Test 7: Security rejection of keys passed (403)');

                              console.log('\n[PASS] All 7 Snowgate Forum & Captcha Gate tests passed with exit code 0!');
                              server.close();
                              process.exit(0);
                            }
                          );
                          reqBad.write(JSON.stringify({ note: 'sk-123456789012345678901234567890' }));
                          reqBad.end();
                        });
                      });
                    });
                  });
                });
              });
            }
          );
          reqGoodPass.write(querystring.stringify({ password: 'two rivers crossing.' }));
          reqGoodPass.end();
        }
      );
      reqBadPass.write(querystring.stringify({ password: 'wrong' }));
      reqBadPass.end();
    });
  });
});
