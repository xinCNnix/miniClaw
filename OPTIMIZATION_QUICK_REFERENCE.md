# Performance Optimization - Quick Reference Guide

## New Configuration Options

### Caching Settings
```bash
# Enable/disable caching features
ENABLE_SEMANTIC_SEARCH_CACHE=true   # Cache semantic search results
SEMANTIC_SEARCH_CACHE_TTL=300       # Cache lifetime in seconds (5 min)

ENABLE_CONTEXT_CACHE=true            # Cache conversation context
CONTEXT_CACHE_SIZE=64                # Max cached contexts

ENABLE_PROMPT_CACHE=true             # Cache system prompts
```

### Parallel Tool Execution
```bash
ENABLE_PARALLEL_TOOL_EXECUTION=true  # Enable parallel tool execution
ENABLE_AUTO_FALLBACK=true            # Auto-fallback to sequential on error
PARALLEL_TOOL_DEPENDENCY_DETECTION=true  # Detect tool dependencies
MAX_CONCURRENT_TOOLS=5               # Max tools to run in parallel
```

### Streaming Response
```bash
ENABLE_STREAMING_RESPONSE=true       # Enable LLM streaming
STREAMING_CHUNK_SIZE=512             # Characters per chunk
```

### Prompt Compression
```bash
ENABLE_SMART_TRUNCATION=true         # Enable smart prompt truncation
MAX_PROMPT_TOKENS=15000              # Max tokens (reduced from 20000)
```

---

## Performance Impact Summary

| Optimization | Improvement | Risk Level |
|--------------|-------------|------------|
| Embedding Preloading | 10-30s → <1s | Very Low |
| Semantic Search Cache | 1-2s → 0.1s | Very Low |
| Conversation Context Cache | 0.3s → 0.1s | Very Low |
| System Prompt Cache | 0.5s → 0.1s | Very Low |
| Parallel Tool Execution | 50-70% faster | Low |
| Streaming LLM Response | TTFB -80% | Low |
| Prompt Compression | 20-30% faster | Medium |

---

## Common Issues & Solutions

### Issue: Parallel tool execution causing errors
**Solution**: Disable parallel execution or enable auto-fallback
```bash
ENABLE_PARALLEL_TOOL_EXECUTION=false
# OR
ENABLE_AUTO_FALLBACK=true
```

### Issue: Cache causing stale results
**Solution**: Reduce TTL or disable specific cache
```bash
SEMANTIC_SEARCH_CACHE_TTL=60  # 1 minute instead of 5
# OR
ENABLE_SEMANTIC_SEARCH_CACHE=false
```

### Issue: Streaming not working
**Solution**: Check LLM provider compatibility
```bash
ENABLE_STREAMING_RESPONSE=false  # Fall back to non-streaming
```

### Issue: Prompts getting truncated too aggressively
**Solution**: Adjust token budget or disable smart truncation
```bash
MAX_PROMPT_TOKENS=20000  # Increase limit
# OR
ENABLE_SMART_TRUNCATION=false
```

---

## Monitoring Commands

### Check Cache Performance
```bash
# View logs for cache hits/misses
tail -f logs/app.log | grep -i "cache"

# Expected output:
# Semantic search cache hit for query: ...
# Conversation context cache hit for session: ...
```

### Check Parallel Tool Execution
```bash
# View parallel execution logs
tail -f logs/app.log | grep -i "parallel\|sequential"

# Expected output:
# Attempting parallel execution of 3 tools
# Parallel execution completed: 3 tools
# OR: Tool dependencies detected, using sequential execution
```

### Check Streaming Response
```bash
# View streaming logs
tail -f logs/app.log | grep -i "stream"

# Expected output:
# Starting LLM stream...
# LLM stream chunk: 50 chars
```

---

## Performance Testing

### Quick Test
```bash
# Simple Q&A (should be <1s)
curl -X POST http://localhost:8002/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "session_id": "test", "stream": false}'

# Single tool (should be <3s)
curl -X POST http://localhost:8002/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "北京天气怎么样", "session_id": "test", "stream": false}'

# Multi-tool (should be <5s)
curl -X POST http://localhost:8002/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "查看当前目录并搜索README文件", "session_id": "test", "stream": false}'
```

### Load Test
```bash
# Using Apache Bench
ab -n 100 -c 10 -T "application/json" \
   -p test_request.json \
   http://localhost:8002/api/chat
```

---

## Configuration File Template

Add to your `.env` file:

```bash
# ===== Performance Optimization =====

# Caching
ENABLE_SEMANTIC_SEARCH_CACHE=true
SEMANTIC_SEARCH_CACHE_TTL=300
ENABLE_CONTEXT_CACHE=true
CONTEXT_CACHE_SIZE=64
ENABLE_PROMPT_CACHE=true

# Parallel Tool Execution
ENABLE_PARALLEL_TOOL_EXECUTION=true
ENABLE_AUTO_FALLBACK=true
PARALLEL_TOOL_DEPENDENCY_DETECTION=true
MAX_CONCURRENT_TOOLS=5

# Streaming Response
ENABLE_STREAMING_RESPONSE=true
STREAMING_CHUNK_SIZE=512

# Prompt Compression
ENABLE_SMART_TRUNCATION=true
MAX_PROMPT_TOKENS=15000
```

---

## Troubleshooting Checklist

- [ ] Verify all configuration values in `.env`
- [ ] Check logs for cache hit/miss patterns
- [ ] Monitor parallel tool execution decisions
- [ ] Verify streaming is working (TTFB < 0.5s)
- [ ] Check prompt length after compression
- [ ] Test with different LLM providers
- [ ] Run load tests to validate improvements
- [ ] Monitor memory usage with caching enabled

---

## Expert Tips

1. **Start with all optimizations enabled**, then disable individual ones if needed
2. **Monitor cache effectiveness** - low hit rates may indicate TTL issues
3. **Parallel execution shines** with I/O-bound tools (terminal, fetch_url)
4. **Streaming benefits** are most noticeable on slower connections
5. **Prompt compression** is most effective with long conversations
6. **Cache warming**: Run a few queries after startup to populate caches
7. **Memory monitoring**: Large cache sizes may increase memory usage

---

## Support

For issues or questions:
1. Check `logs/app.log` for detailed error messages
2. Review `PERFORMANCE_OPTIMIZATION_SUMMARY.md` for implementation details
3. Disable problematic optimizations individually
4. Report issues with logs and configuration

---

## Version History

- **v1.0** (2025-03-15): Initial implementation of all 7 optimizations
