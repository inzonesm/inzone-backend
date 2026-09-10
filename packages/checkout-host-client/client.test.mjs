import test from 'node:test';
import assert from 'node:assert/strict';
import { createCheckoutClient } from './index.js';
const input = {offerId:'lives',catalogVersion:'v1',requestId:'persisted-1'};
const response = (data={}, status=200) => new Response(JSON.stringify({success:true,data}),{status});
function fixture(fetcher, extra={}) {
  return createCheckoutClient({baseUrl:'https://api.example.test',gameId:'game-1',getToken:async()=> 'fixture-token',fetch:fetcher,...extra});
}
test('catalog is public and uses exact existing path',async()=>{
  let tokens=0;
  const c=fixture(async(url,options)=>{
    assert.equal(url,'https://api.example.test/api/game-sdk/v2/games/game-1/catalog');
    assert.equal(options.headers.Authorization,undefined);
    assert.equal(options.credentials,'omit');assert.equal(options.redirect,'error');
    assert.equal(options.cache,'no-store');return response({version:'v1'});
  },{getToken:()=>{tokens++;return 'secret';}});
  assert.deepEqual(await c.getCatalog(),{version:'v1'});assert.equal(tokens,0);
});
test('purchase keeps exact caller binding and token only in header',async()=>{
  const c=fixture(async(url,options)=>{
    assert.equal(options.method,'POST');assert.equal(options.headers.Authorization,'Bearer fixture-token');
    assert.deepEqual(JSON.parse(options.body),input);assert.ok(!url.includes('fixture-token'));
    return response({transactionId:'receipt'});
  });assert.deepEqual(await c.purchase(input),{transactionId:'receipt'});
});
test('receipt and inventory paths obtain fresh tokens',async()=>{
  let tokens=0;const paths=[];
  const c=fixture(async(url,options)=>{paths.push(url);assert.equal(options.headers.Authorization,'Bearer token-'+tokens);return response();},{getToken:()=> 'token-'+(++tokens)});
  await c.getReceipt('persisted-1');await c.getInventory('lives');
  assert.ok(paths[0].endsWith('/purchases/persisted-1'));assert.ok(paths[1].endsWith('/inventory/lives'));assert.equal(tokens,2);
});
test('missing auth prevents request; provider errors do not expose token',async()=>{
  let calls=0;const fetcher=async()=>{calls++;return response();};
  await assert.rejects(fixture(fetcher,{getToken:()=>null}).purchase(input),{code:'UNAUTHENTICATED',outcomeUnknown:false});
  await assert.rejects(fixture(fetcher,{getToken:()=>{throw Error('private-token');}}).purchase(input),{message:'AUTH_UNAVAILABLE'});
  assert.equal(calls,0);
});
test('rejects malformed IDs, client price and insecure/token-bearing origins before fetch',()=>{
  let calls=0;const c=fixture(async()=>{calls++;return response();});
  assert.throws(()=>c.purchase({...input,coins:1}),{code:'INVALID_REQUEST'});
  assert.throws(()=>c.getReceipt('../escape'),{code:'INVALID_IDENTIFIER'});
  assert.throws(()=>c.purchase({...input,requestId:''}),{code:'INVALID_IDENTIFIER'});
  for(const baseUrl of ['http://external.test','https://user:secret@api.test','https://api.test?token=x','https://api.test/path']) {
    assert.throws(()=>fixture(()=>{}, {baseUrl}),{code:'INVALID_BASE_URL'});
  }assert.equal(calls,0);
});
test('preserves disabled/stale-price errors without retrying',async()=>{
  for(const [code,status] of [['CHECKOUT_DISABLED',404],['OFFER_CHANGED',409],['INSUFFICIENT_BALANCE',400]]) {
    let calls=0;const c=fixture(async()=>{calls++;return new Response(JSON.stringify({success:false,code}),{status});});
    await assert.rejects(c.purchase(input),{code,status,outcomeUnknown:false});assert.equal(calls,1);
  }
});
test('network failure is unknown purchase outcome; no automatic retry',async()=>{
  let calls=0;const c=fixture(async()=>{calls++;throw Error('secret network details');});
  await assert.rejects(c.purchase(input),{code:'NETWORK_ERROR',outcomeUnknown:true,message:'NETWORK_ERROR'});assert.equal(calls,1);
  await assert.rejects(c.getReceipt(input.requestId),{code:'NETWORK_ERROR',outcomeUnknown:false});
});
test('server/malformed response after POST requires recovery',async()=>{
  await assert.rejects(fixture(async()=>new Response('bad',{status:502})).purchase(input),{code:'INVALID_RESPONSE',outcomeUnknown:true});
  await assert.rejects(fixture(async()=>new Response(JSON.stringify({success:false,code:'CHECKOUT_UNAVAILABLE'}),{status:503})).purchase(input),{code:'CHECKOUT_UNAVAILABLE',outcomeUnknown:true});
  await assert.rejects(fixture(async()=>response(null)).purchase(input),{code:'INVALID_RESPONSE',outcomeUnknown:true});
});
test('timeout bounds stalled token resolution and prevents late purchase',async()=>{
  let release;let calls=0;
  const c=fixture(async()=>{calls++;return response();},{timeoutMs:10,getToken:()=>new Promise(resolve=>{release=resolve;})});
  await assert.rejects(c.purchase(input),{code:'REQUEST_TIMEOUT',outcomeUnknown:false});
  release('late-token');await new Promise(resolve=>setTimeout(resolve,5));assert.equal(calls,0);
});
test('timeout after dispatch reports unknown and aborts transport',async()=>{
  let signal;const c=fixture(async(_,options)=>{signal=options.signal;return new Promise(()=>{});},{timeoutMs:10});
  await assert.rejects(c.purchase(input),{code:'REQUEST_TIMEOUT',outcomeUnknown:true});assert.equal(signal.aborted,true);
});
test('cancellation before dispatch does not charge; after dispatch requires recovery',async()=>{
  let calls=0;const before=new AbortController();before.abort();
  await assert.rejects(fixture(async()=>{calls++;return response();}).purchase(input,{signal:before.signal}),{code:'REQUEST_ABORTED',outcomeUnknown:false});assert.equal(calls,0);
  const after=new AbortController();
  const c=fixture(async()=>{queueMicrotask(()=>after.abort());return new Promise(()=>{});});
  await assert.rejects(c.purchase(input,{signal:after.signal}),{code:'REQUEST_ABORTED',outcomeUnknown:true});
});
test('explicit recovery uses original ID and never resubmits purchase',async()=>{
  const methods=[];const c=fixture(async(url,options)=>{methods.push(options.method);if(options.method==='POST')throw Error('connection lost');assert.ok(url.endsWith('/purchases/persisted-1'));return response({transactionId:'committed'});});
  await assert.rejects(c.purchase(input));assert.equal((await c.getReceipt(input.requestId)).transactionId,'committed');assert.deepEqual(methods,['POST','GET']);
});
