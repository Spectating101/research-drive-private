# Content Analysis Engine

A portable, content-agnostic engine for analyzing and synthesizing information from multiple sources using LLM-powered consensus formation.

## <ENGINE_OVERVIEW>

### **Core Purpose**

Extract, analyze, and synthesize content from multiple sources to form intelligent consensus and insights. Originally developed for academic research, now generalized for any content type (news, articles, reports, etc.).

### **Key Capabilities**

- **Multi-Source Analysis**: Process and analyze content from various sources
- **LLM-Powered Synthesis**: Form intelligent consensus across multiple pieces of content
- **Smart Dispatcher**: Automatically select appropriate analysis depth based on user intent
- **Citation Tracking**: Track sources and provide provenance for all insights
- **Session Management**: Maintain context across analysis sessions
- **Caching & Performance**: Redis-based caching for improved performance

---

## <ARCHITECTURE>

### **Core Components**

```
engine/
├── src/
│   ├── services/
│   │   ├── research_service/
│   │   │   ├── synthesizer.py          # Core consensus formation engine
│   │   │   ├── dispatcher.py           # Smart engine selection logic
│   │   │   └── context_manager.py      # Session and content management
│   │   └── llm_service/
│   │       ├── llm_manager.py          # LLM orchestration and routing
│   │       ├── model_dispatcher.py     # Provider selection and fallback
│   │       ├── processors.py           # Content processing utilities
│   │       ├── embeddings.py           # Vector embeddings for similarity
│   │       ├── usage_tracker.py        # Usage monitoring and limits
│   │       └── api_clients/            # LLM provider integrations
│   ├── storage/
│   │   └── db/                         # Database operations and models
│   ├── utils/
│   │   └── logger.py                   # Structured logging
│   └── config/                         # Configuration management
├── requirements.txt                    # Dependencies
└── README.md                          # This file
```

### **Data Flow**

1. **Input**: Content items (articles, news, papers, etc.)
2. **Processing**: Content is processed, summarized, and stored
3. **Analysis**: LLM-powered analysis extracts insights, contradictions, gaps
4. **Synthesis**: Consensus formation across multiple sources
5. **Output**: Structured insights with citations and provenance

---

## <USAGE>

### **Basic Usage**

```python
import asyncio
from src.services.research_service.synthesizer import ContentSynthesizer
from src.services.llm_service.llm_manager import LLMManager
from src.storage.db.operations import DatabaseOperations

async def analyze_content():
    # Initialize components
    db_ops = DatabaseOperations()
    llm_manager = LLMManager("redis://localhost:6379")
    synthesizer = ContentSynthesizer(db_ops, llm_manager, "redis://localhost:6379")

    # Content IDs to analyze
    content_ids = ["article_1", "article_2", "article_3"]

    # Synthesize content
    results = await synthesizer.synthesize_content(
        content_ids=content_ids,
        content_type="news",
        force_refresh=False
    )

    print(f"Analysis complete: {results['content_count']} items processed")
    print(f"Common findings: {len(results['common_findings'])}")
    print(f"Contradictions: {len(results['contradictions'])}")
    print(f"Gaps identified: {len(results['gaps'])}")

# Run analysis
asyncio.run(analyze_content())
```

### **Session Management**

```python
from src.services.research_service.context_manager import ContentContextManager

async def manage_session():
    context_manager = ContentContextManager(db_ops, llm_manager, "redis://localhost:6379")

    # Create session
    session = await context_manager.create_session("session_123", "news")

    # Add content
    content_item = {
        "title": "Breaking News Article",
        "content": "Article content here...",
        "source": "News Source",
        "url": "https://example.com/article",
        "date": "2024-01-01T00:00:00Z"
    }

    success = await context_manager.add_content_to_session("session_123", content_item)

    # Get session content
    content_items = await context_manager.get_session_content("session_123")

    # Close session
    await context_manager.close_session("session_123")
```

### **Smart Dispatcher**

```python
from src.services.research_service.dispatcher import select_research_engine

async def use_dispatcher():
    user_message = "What are the latest developments in AI?"
    history = [{"role": "user", "content": "Tell me about AI"}]
    user_profile = {"prefers_deep_analysis": True}

    engine_name, results = await select_research_engine(
        user_message=user_message,
        history=history,
        user_profile=user_profile,
        llm_manager=llm_manager
    )

    print(f"Selected engine: {engine_name}")
    print(f"Results: {results}")
```

---

## <ADAPTATION_GUIDE>

### **For News Analysis**

1. **Content Retrieval**: Replace academic paper retrieval with news API integration
2. **Temporal Analysis**: Add timeline analysis for news events
3. **Source Credibility**: Implement source credibility scoring
4. **Breaking News**: Add real-time monitoring capabilities

### **For Business Intelligence**

1. **Market Data**: Integrate market data sources
2. **Competitor Analysis**: Add competitor monitoring
3. **Trend Analysis**: Implement trend detection algorithms
4. **Executive Summaries**: Generate executive-level insights

### **For Legal Research**

1. **Case Law**: Integrate legal database APIs
2. **Precedent Analysis**: Add precedent identification
3. **Regulatory Tracking**: Monitor regulatory changes
4. **Citation Networks**: Build legal citation networks

### **For Scientific Research**

1. **Paper Retrieval**: Integrate academic databases (PubMed, arXiv, etc.)
2. **Methodology Analysis**: Add methodology comparison
3. **Reproducibility**: Track reproducibility indicators
4. **Peer Review**: Integrate peer review data

---

## <CONFIGURATION>

### **Environment Variables**

```bash
# Redis Configuration
REDIS_URL=redis://localhost:6379

# LLM Provider Configuration
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
GOOGLE_API_KEY=your_google_key

# Database Configuration
MONGODB_URI=mongodb://localhost:27017
DATABASE_NAME=content_engine

# Logging
LOG_LEVEL=INFO
```

### **LLM Provider Setup**

The engine supports multiple LLM providers with automatic fallback:

1. **OpenAI**: GPT-4, GPT-3.5-turbo
2. **Anthropic**: Claude-3, Claude-2
3. **Google**: Gemini Pro, Gemini Flash
4. **Local**: Ollama, LM Studio

Configure providers in `src/config/llm_config.py`

---

## <DEPLOYMENT>

### **Docker Deployment**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ ./src/
COPY config/ ./config/

CMD ["python", "-m", "src.main"]
```

### **Kubernetes Deployment**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: content-engine
spec:
  replicas: 3
  selector:
    matchLabels:
      app: content-engine
  template:
    metadata:
      labels:
        app: content-engine
    spec:
      containers:
        - name: content-engine
          image: content-engine:latest
          env:
            - name: REDIS_URL
              value: "redis://redis-service:6379"
            - name: MONGODB_URI
              value: "mongodb://mongo-service:27017"
```

---

## <PERFORMANCE>

### **Optimization Strategies**

1. **Caching**: Redis-based caching for synthesis results
2. **Parallel Processing**: Concurrent analysis of multiple content items
3. **Batch Processing**: Process content in batches for efficiency
4. **Resource Management**: Automatic cleanup of expired sessions

### **Scaling Considerations**

- **Horizontal Scaling**: Stateless design allows multiple instances
- **Database Sharding**: Shard by content type or date
- **CDN Integration**: Cache static content and results
- **Load Balancing**: Distribute requests across instances

---

## <MONITORING>

### **Health Checks**

```python
# Check engine health
health = await synthesizer.health_check()
print(f"Engine status: {health['status']}")

# Monitor usage
usage = await llm_manager.usage_tracker.get_usage_stats()
print(f"API calls: {usage['total_calls']}")
```

### **Metrics**

- **Processing Time**: Time to analyze content
- **Cache Hit Rate**: Redis cache effectiveness
- **API Usage**: LLM provider usage and costs
- **Error Rates**: Processing error frequency
- **User Satisfaction**: Response quality metrics

---

## <SECURITY>

### **Data Protection**

- **Input Validation**: All inputs are validated and sanitized
- **Access Control**: Role-based access to sensitive operations
- **Audit Logging**: Complete audit trail of all operations
- **Encryption**: Data encrypted in transit and at rest

### **LLM Security**

- **Prompt Injection Protection**: Sanitize all LLM inputs
- **Output Validation**: Validate LLM outputs before processing
- **Rate Limiting**: Prevent abuse of LLM APIs
- **Cost Monitoring**: Track and limit LLM usage costs

---

## <DEVELOPMENT>

### **Adding New Content Types**

1. **Extend Content Model**: Add new fields to content schema
2. **Update Processing**: Modify content processing logic
3. **Add Analysis**: Create content-specific analysis methods
4. **Update Dispatcher**: Add content type detection logic

### **Adding New LLM Providers**

1. **Create API Client**: Implement provider-specific client
2. **Add Configuration**: Add provider configuration
3. **Update Dispatcher**: Add provider to routing logic
4. **Test Integration**: Verify provider integration

### **Testing**

```bash
# Run unit tests
python -m pytest tests/

# Run integration tests
python -m pytest tests/integration/

# Run performance tests
python -m pytest tests/performance/
```

---

## <TROUBLESHOOTING>

### **Common Issues**

1. **Redis Connection**: Check Redis URL and connectivity
2. **LLM API Limits**: Monitor API usage and rate limits
3. **Memory Usage**: Monitor memory usage for large content
4. **Processing Time**: Check for slow LLM responses

### **Debug Mode**

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable debug logging for specific components
logger = logging.getLogger('src.services.research_service.synthesizer')
logger.setLevel(logging.DEBUG)
```

---

## <LICENSE>

This engine is provided as-is for educational and development purposes. Please ensure compliance with all applicable licenses for LLM providers and data sources used.

---

## <SUPPORT>

For questions, issues, or contributions:

1. **Documentation**: Check this README and inline code comments
2. **Issues**: Create detailed issue reports with error logs
3. **Contributions**: Submit pull requests with tests and documentation
4. **Community**: Join discussions in the project repository

---

_This engine represents the core methodology of feeding LLMs multiple materials, extracting summaries and key points, and synthesizing consensus - adapted for portability and extensibility across different content domains._
