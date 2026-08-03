#!/usr/bin/env python3
"""
Example usage of the Content Analysis Engine

This script demonstrates how to use the engine to analyze and synthesize content
from multiple sources.
"""

import asyncio
import os
from datetime import datetime
from src.services.research_service.synthesizer import ContentSynthesizer
from src.services.research_service.context_manager import ContentContextManager
from src.services.research_service.dispatcher import select_research_engine
from src.services.llm_service.llm_manager import LLMManager
from src.storage.db.operations import DatabaseOperations

async def example_content_analysis():
    """Example of analyzing multiple content sources."""
    
    print("🚀 Starting Content Analysis Engine Example")
    print("=" * 50)
    
    # Initialize components
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    db_ops = DatabaseOperations()
    llm_manager = LLMManager(redis_url)
    synthesizer = ContentSynthesizer(db_ops, llm_manager, redis_url)
    context_manager = ContentContextManager(db_ops, llm_manager, redis_url)
    
    # Example content items (in a real scenario, these would come from your data sources)
    example_content = [
        {
            "title": "AI Breakthrough in Medical Diagnosis",
            "content": "Researchers have developed a new AI system that can diagnose diseases with 95% accuracy. The system uses deep learning algorithms to analyze medical images and patient data. This represents a significant improvement over traditional diagnostic methods.",
            "source": "Medical Research Journal",
            "url": "https://example.com/ai-medical",
            "date": "2024-01-15T10:00:00Z",
            "content_type": "research"
        },
        {
            "title": "AI Ethics Concerns Raised by Experts",
            "content": "Leading AI ethicists are warning about the potential risks of AI systems in healthcare. They argue that while AI can improve diagnosis, it may also introduce biases and reduce human oversight. More regulation is needed.",
            "source": "Tech Ethics Forum",
            "url": "https://example.com/ai-ethics",
            "date": "2024-01-16T14:30:00Z",
            "content_type": "opinion"
        },
        {
            "title": "AI Adoption in Healthcare Accelerates",
            "content": "Hospitals worldwide are rapidly adopting AI diagnostic tools. The market for AI in healthcare is expected to reach $45 billion by 2027. Early adopters report improved patient outcomes and reduced costs.",
            "source": "Healthcare Industry Report",
            "url": "https://example.com/ai-adoption",
            "date": "2024-01-17T09:15:00Z",
            "content_type": "industry"
        }
    ]
    
    print("📝 Creating analysis session...")
    
    # Create a session
    session = await context_manager.create_session("example_session_001", "mixed")
    print(f"✅ Session created: {session['session_id']}")
    
    # Add content to session
    print("\n📄 Adding content to session...")
    for i, content in enumerate(example_content, 1):
        success = await context_manager.add_content_to_session("example_session_001", content)
        if success:
            print(f"✅ Added content {i}: {content['title']}")
        else:
            print(f"❌ Failed to add content {i}")
    
    # Get session content
    print("\n🔍 Retrieving session content...")
    content_items = await context_manager.get_session_content("example_session_001")
    print(f"✅ Retrieved {len(content_items)} content items")
    
    # Synthesize content
    print("\n🧠 Synthesizing content...")
    if content_items:
        content_ids = [item.get('id', f"item_{i}") for i, item in enumerate(content_items)]
        
        synthesis_results = await synthesizer.synthesize_content(
            content_ids=content_ids,
            content_type="mixed",
            force_refresh=False
        )
        
        print("\n📊 Synthesis Results:")
        print("-" * 30)
        print(f"Content analyzed: {synthesis_results.get('content_count', 0)} items")
        print(f"Content type: {synthesis_results.get('content_type', 'unknown')}")
        print(f"Generated at: {synthesis_results.get('generated_at', 'unknown')}")
        
        # Display common findings
        common_findings = synthesis_results.get('common_findings', [])
        if common_findings:
            print(f"\n🔍 Common Findings ({len(common_findings)}):")
            for i, finding in enumerate(common_findings, 1):
                print(f"  {i}. {finding.get('description', 'No description')}")
        
        # Display contradictions
        contradictions = synthesis_results.get('contradictions', [])
        if contradictions:
            print(f"\n⚠️  Contradictions ({len(contradictions)}):")
            for i, contradiction in enumerate(contradictions, 1):
                print(f"  {i}. {contradiction.get('description', 'No description')}")
        
        # Display gaps
        gaps = synthesis_results.get('gaps', [])
        if gaps:
            print(f"\n🕳️  Gaps Identified ({len(gaps)}):")
            for i, gap in enumerate(gaps, 1):
                print(f"  {i}. {gap.get('description', 'No description')}")
        
        # Display timeline
        timeline = synthesis_results.get('timeline', {})
        if timeline and 'timeline' in timeline:
            print(f"\n📅 Timeline Analysis:")
            print(f"  {timeline.get('timeline', 'No timeline data')}")
        
        # Display connections
        connections = synthesis_results.get('connections', {})
        if connections and 'connections' in connections:
            print(f"\n🔗 Content Connections:")
            print(f"  {connections.get('connections', 'No connection data')}")
    
    # Demonstrate dispatcher
    print("\n🎯 Testing Smart Dispatcher...")
    user_message = "What are the latest developments in AI healthcare?"
    history = [{"role": "user", "content": "Tell me about AI"}]
    user_profile = {"prefers_deep_analysis": True}
    
    engine_name, results = await select_research_engine(
        user_message=user_message,
        history=history,
        user_profile=user_profile,
        llm_manager=llm_manager
    )
    
    print(f"✅ Dispatcher selected engine: {engine_name}")
    print(f"📋 Results preview: {results.get('summary', 'No summary')[:100]}...")
    
    # Close session
    print("\n🔚 Closing session...")
    await context_manager.close_session("example_session_001")
    print("✅ Session closed")
    
    # Cleanup
    print("\n🧹 Cleaning up...")
    await synthesizer.cleanup()
    print("✅ Cleanup complete")
    
    print("\n🎉 Example completed successfully!")
    print("=" * 50)

async def example_health_check():
    """Example of checking engine health."""
    
    print("\n🏥 Health Check Example")
    print("-" * 30)
    
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    db_ops = DatabaseOperations()
    llm_manager = LLMManager(redis_url)
    synthesizer = ContentSynthesizer(db_ops, llm_manager, redis_url)
    
    # Check health
    health = await synthesizer.health_check()
    
    print("Engine Health Status:")
    print(f"  Status: {health.get('status', 'unknown')}")
    print(f"  Redis: {health.get('redis', 'unknown')}")
    print(f"  LLM: {health.get('llm', 'unknown')}")
    print(f"  Cache Size: {health.get('cache_size', 0)}")
    print(f"  Active Tasks: {health.get('active_tasks', 0)}")
    
    if health.get('error'):
        print(f"  Error: {health['error']}")
    
    await synthesizer.cleanup()

if __name__ == "__main__":
    # Set up environment variables if not already set
    if not os.environ.get('REDIS_URL'):
        os.environ['REDIS_URL'] = 'redis://localhost:6379'
    
    # Run examples
    asyncio.run(example_content_analysis())
    asyncio.run(example_health_check()) 