from services.intent import classify
from services.local_tools import try_local

# Test chat-only short circuit
i = classify('thanks!')
assert i.is_chat_only, f'chat-only failed: {i}'
print('PASS: chat-only')

# Test math detection
i = classify('what is 47 * 89?')
assert i.math_expr is not None, f'math_expr not detected: {i}'
print('PASS: math_expr:', i.math_expr)

# Test time query
i = classify('what time is it in Tokyo?')
assert i.time_query, f'time query failed: {i}'
assert not i.needs_web, f'time should not need web: {i}'
print('PASS: time query')

# Test stock mis-fire guard
i = classify('how does AI affect the US economy?')
assert i.stock_ticker is None, f'stock mis-fire: ticker={i.stock_ticker}'
print('PASS: stock mis-fire guard')

# Test stock explicit 
i = classify('AAPL stock price today')
print('stock ticker (explicit):', i.stock_ticker)
print('needs_web:', i.needs_web)

# Test cashtag
i = classify('what is $AAPL trading at?')
print('stock ticker (cashtag):', i.stock_ticker)

# Test local_tools
r = try_local('split $240 3 ways with 18% tip')
print('tip_split:', r)
assert r is not None and r['kind'] == 'tip_split'
print('PASS: tip_split')

r = try_local('sha256 of hello')
print('hash:', r['kind'] if r else None, r['result'][:20] if r else None)
assert r is not None and r['kind'] == 'hash'
print('PASS: hash')

r = try_local('days until Christmas')
print('date:', r)
assert r is not None and r['kind'] == 'date'
print('PASS: date')

r = try_local('255 in hex')
print('base_conv:', r)
assert r is not None and r['kind'] == 'base_conv'
print('PASS: base_conv')

print('\nAll smoke tests passed!')
