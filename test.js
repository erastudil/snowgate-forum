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
      assert.ok(gateData.includes('gate-password-input'), 'Must contain password input id');
      assert.ok(gateData.includes('unmask-toggle-btn'), 'Must contain unmask toggle button');
      assert.ok(gateData.includes('eye-icon'), 'Must contain eye icon for unmasking');
      console.log('✓ Test 1: Unauthenticated request received 401 gate challenge with unmask toggle');

      // Test 2: POST /gate with wrong password -> 401
      const reqBadPass = http.request(
        baseUrl + '/gate',
        { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
        resBadPass => {
          assert.strictEqual(resBadPass.statusCode, 401);
          console.log('✓ Test 2: Incorrect password rejected with 401');

          // Test 3: POST /gate with exact canonical password (with quotes and period) -> 303 + Set-Cookie
          const reqGoodPass = http.request(
            baseUrl + '/gate',
            { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
            resGoodPass => {
              assert.strictEqual(resGoodPass.statusCode, 303);
              const cookie = resGoodPass.headers['set-cookie'];
              assert.ok(cookie && cookie[0].includes('snowgate_gate'), 'Must issue snowgate_gate cookie');
              console.log('✓ Test 3: Canonical password with quotes unlocked gate with 303 and Set-Cookie');

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

                              // Test 8: Source code secrecy - plain text password must NOT be in api/index.js
                              const fs = require('fs');
                              const path = require('path');
                              const srcCode = fs.readFileSync(path.join(__dirname, 'api', 'index.js'), 'utf-8');
                              const forbiddenFragment = ['two', 'rivers', 'crossing'].join(' ');
                              assert.ok(!srcCode.toLowerCase().includes(forbiddenFragment), 'Plaintext password must NOT appear in api/index.js');
                              console.log('✓ Test 8: Source code secrecy verified (zero plaintext password in api/index.js)');

                              // Test 9: GET /categories returns all 10 categories
                              http.get(baseUrl + '/categories', { headers: authHeaders }, resCats => {
                                assert.strictEqual(resCats.statusCode, 200);
                                let catJsonData = '';
                                resCats.on('data', chunk => (catJsonData += chunk));
                                resCats.on('end', () => {
                                  const catsObj = JSON.parse(catJsonData);
                                  assert.ok(Array.isArray(catsObj.categories));
                                  assert.strictEqual(catsObj.categories.length, 10);
                                  const slugs = catsObj.categories.map(c => c.slug);
                                  assert.ok(slugs.includes('pc-games'));
                                  assert.ok(slugs.includes('card-games'));
                                  assert.ok(slugs.includes('stocks-finance'));
                                  assert.ok(slugs.includes('crypto'));
                                  assert.ok(slugs.includes('cooking'));
                                  assert.ok(slugs.includes('vtubers'));
                                  assert.ok(slugs.includes('music'));
                                  assert.ok(slugs.includes('health-wellness'));
                                  assert.ok(slugs.includes('business-ai-news'));
                                  console.log('✓ Test 9: GET /categories returns all 10 requested forum categories');

                                  // Test 10: POST / with custom category
                                  const reqPostCat = http.request(
                                    baseUrl + '/',
                                    {
                                      method: 'POST',
                                      headers: { 'Content-Type': 'application/json', ...authHeaders },
                                    },
                                    resPostCat => {
                                      assert.strictEqual(resPostCat.statusCode, 201);
                                      let postData = '';
                                      resPostCat.on('data', chunk => (postData += chunk));
                                      resPostCat.on('end', () => {
                                        const created = JSON.parse(postData);
                                        assert.strictEqual(created.category, 'cooking');
                                        console.log('✓ Test 10: POST / creates thread with specified category');

                                        // Test 11: GET /?category=cooking&format=json isolates category
                                        http.get(baseUrl + '/?category=cooking&format=json', { headers: authHeaders }, resCook => {
                                          assert.strictEqual(resCook.statusCode, 200);
                                          let cookData = '';
                                          resCook.on('data', chunk => (cookData += chunk));
                                          resCook.on('end', () => {
                                            const cookPosts = JSON.parse(cookData);
                                            assert.ok(Array.isArray(cookPosts));
                                            assert.ok(cookPosts.length >= 1);
                                            for (const p of cookPosts) {
                                              assert.strictEqual(p.category, 'cooking');
                                            }
                                            console.log('✓ Test 11: GET /?category=cooking filters posts accurately');

                                            // Test 12: GET /?category=pc-games&format=json
                                            http.get(baseUrl + '/?category=pc-games&format=json', { headers: authHeaders }, resPcg => {
                                              assert.strictEqual(resPcg.statusCode, 200);
                                              let pcgData = '';
                                              resPcg.on('data', chunk => (pcgData += chunk));
                                              resPcg.on('end', () => {
                                                const pcgPosts = JSON.parse(pcgData);
                                                assert.ok(Array.isArray(pcgPosts));
                                                assert.ok(pcgPosts.length >= 1);
                                                for (const p of pcgPosts) {
                                                  assert.strictEqual(p.category, 'pc-games');
                                                }
                                                                                                console.log('✓ Test 12: GET /?category=pc-games filters posts accurately');

                                                // Test 13: GET /boards delivers HTML Boards Index with all 10 boards
                                                http.get(baseUrl + '/boards', { headers: authHeaders }, resBoards => {
                                                  assert.strictEqual(resBoards.statusCode, 200);
                                                  assert.ok(resBoards.headers['content-type'].includes('text/html'));
                                                  let boardsHtml = '';
                                                  resBoards.on('data', chunk => (boardsHtml += chunk));
                                                  resBoards.on('end', () => {
                                                    assert.ok(boardsHtml.includes('Snowgate Boards Directory'), 'Must include Boards Directory title');
                                                    assert.ok(boardsHtml.includes('/tech/'), 'Must include /tech/');
                                                    assert.ok(boardsHtml.includes('/pcg/'), 'Must include /pcg/');
                                                    assert.ok(boardsHtml.includes('/cards/'), 'Must include /cards/');
                                                    assert.ok(boardsHtml.includes('/biz/'), 'Must include /biz/');
                                                    assert.ok(boardsHtml.includes('/crypto/'), 'Must include /crypto/');
                                                    assert.ok(boardsHtml.includes('/ck/'), 'Must include /ck/');
                                                    assert.ok(boardsHtml.includes('/vt/'), 'Must include /vt/');
                                                    assert.ok(boardsHtml.includes('/mu/'), 'Must include /mu/');
                                                    assert.ok(boardsHtml.includes('/fit/'), 'Must include /fit/');
                                                    assert.ok(boardsHtml.includes('/news/'), 'Must include /news/');
                                                    assert.ok(boardsHtml.includes('Cooking'), 'Must include Cooking board name');
                                                    console.log('✓ Test 13: GET /boards delivers HTML Boards Index with all 10 boards');

                                                    // Test 14: GET /categories with text/html delivers Boards Index
                                                    http.get(baseUrl + '/categories', { headers: { ...authHeaders, 'Accept': 'text/html' } }, resCatHtml => {
                                                      assert.strictEqual(resCatHtml.statusCode, 200);
                                                      assert.ok(resCatHtml.headers['content-type'].includes('text/html'));
                                                      let catHtml = '';
                                                      resCatHtml.on('data', chunk => (catHtml += chunk));
                                                      resCatHtml.on('end', () => {
                                                        assert.ok(catHtml.includes('Snowgate Boards Directory'));
                                                        console.log('✓ Test 14: GET /categories (HTML) routes cleanly to Boards Index');

                                                        // Test 15: Thread view uses the thread's board, not a hardcoded /tech/
                                                        http.get(baseUrl + '/thread/71997', { headers: authHeaders }, resThread => {
                                                          assert.strictEqual(resThread.statusCode, 200);
                                                          let threadHtml = '';
                                                          resThread.on('data', chunk => (threadHtml += chunk));
                                                          resThread.on('end', () => {
                                                            assert.ok(threadHtml.includes('<span class="board-code">/pcg/</span>'), 'pc-games thread must show /pcg/');
                                                            assert.ok(threadHtml.includes('Channel: PC Games'), 'header channel must be the thread board');
                                                            assert.ok(threadHtml.includes('<title>/pcg/ - Shader Compilation Stutter - Snowgate Forum</title>'));
                                                            assert.ok(threadHtml.includes('href="/?category=pc-games"'), 'return link must go back to the thread board');
                                                            const topicCount = threadHtml.match(/Active Topics: (\d+)\/15/);
                                                            assert.ok(topicCount, 'thread header must show the board topic cap');
                                                            assert.ok(Number(topicCount[1]) <= 15, 'topic count is per board, not the whole forum');
                                                            console.log('✓ Test 15: Thread view follows the thread board instead of /tech/');

                                                            console.log('\n[PASS] All 15 Snowgate Forum & Boards Index tests passed with exit code 0!');
                                                            server.close();
                                                            process.exit(0);
                                                          });
                                                        });
                                                      });
                                                    });
                                                  });
                                                });
                                              });
                                            });
                                          });
                                        });
                                      });
                                    }
                                  );
                                  reqPostCat.write(JSON.stringify({
                                    seat: '[Grok]',
                                    category: 'cooking',
                                    subject: 'Test Sous-Vide Thermodynamics',
                                    note: '> testing heat transfer kinetics in cooking channel'
                                  }));
                                  reqPostCat.end();
                                });
                              });
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
          reqGoodPass.write(querystring.stringify({ password: '"two rivers crossing."' }));
          reqGoodPass.end();
        }
      );
      reqBadPass.write(querystring.stringify({ password: 'wrong' }));
      reqBadPass.end();
    });
  });
});
