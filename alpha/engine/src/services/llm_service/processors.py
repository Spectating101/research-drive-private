import logging
import re
import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime
import hashlib

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chat_models import ChatOpenAI
import tiktoken

# Configure structured logging
logger = logging.getLogger(__name__)

class DocumentProcessor:
    """
    Enhanced document processor with comprehensive error handling, security, and observability.
    
    Features:
    - Secure text processing and chunking
    - Input validation and sanitization
    - Comprehensive error handling and retry logic
    - Structured logging and monitoring
    - Protection against injection attacks
    """
    
    def __init__(self, max_chunk_size: int = 1000, chunk_overlap: int = 200):
        """
        Initialize document processor with enhanced security and error handling.
        
        Args:
            max_chunk_size: Maximum size of text chunks
            chunk_overlap: Overlap between chunks
            
        Raises:
            ValueError: If parameters are invalid
        """
        try:
            if max_chunk_size <= 0 or chunk_overlap < 0:
                raise ValueError("Invalid chunk parameters")
            
            logger.info("Initializing DocumentProcessor with enhanced security")
            
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=max_chunk_size,
                chunk_overlap=chunk_overlap,
                length_function=len,
                separators=["\n\n", "\n", " ", ""]
            )
            
            # Initialize LLM with error handling
            try:
                self.llm = ChatOpenAI(temperature=0)
                logger.info("LLM client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize LLM client: {str(e)}")
                raise
            
            # Initialize tokenizer with error handling
            try:
                self.tokenizer = tiktoken.get_encoding("cl100k_base")
                logger.info("Tokenizer initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize tokenizer: {str(e)}")
                raise
            
            logger.info("DocumentProcessor initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize DocumentProcessor: {str(e)}")
            raise
    
    def _validate_input(self, content: str, max_length: int = 1000000) -> None:
        """
        Validate input content for security and safety.
        
        Args:
            content: Content to validate
            max_length: Maximum allowed length
            
        Raises:
            ValueError: If content is invalid
        """
        if not isinstance(content, str):
            raise ValueError("Content must be a string")
        
        if not content.strip():
            raise ValueError("Content cannot be empty")
        
        if len(content) > max_length:
            raise ValueError(f"Content too long (max {max_length} characters)")
        
        # Check for potentially dangerous content
        dangerous_patterns = [
            r'<script.*?>.*?</script>',  # Script tags
            r'javascript:',              # JavaScript protocol
            r'data:text/html',           # Data URLs
            r'vbscript:',                # VBScript
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                raise ValueError(f"Content contains potentially dangerous patterns: {pattern}")
    
    def _sanitize_content(self, content: str) -> str:
        """
        Sanitize content to prevent injection attacks.
        
        Args:
            content: Content to sanitize
            
        Returns:
            Sanitized content
        """
        # Basic XSS protection
        sanitized = content.replace('<', '&lt;').replace('>', '&gt;')
        
        # Remove null bytes and other control characters
        sanitized = ''.join(char for char in sanitized if ord(char) >= 32 or char in '\n\r\t')
        
        return sanitized.strip()
    
    async def process_document(self, content: str) -> Dict[str, Any]:
        """
        Process document content with enhanced error handling and security.
        
        Args:
            content: Document content to process
            
        Returns:
            Processing results with chunks and summary
            
        Raises:
            ValueError: If content is invalid
            ConnectionError: If LLM processing fails
        """
        try:
            # Input validation and sanitization
            self._validate_input(content)
            sanitized_content = self._sanitize_content(content)
            
            logger.info(f"Processing document content (length: {len(sanitized_content)})")
            
            # Split into chunks with error handling
            try:
                chunks = self.text_splitter.split_text(sanitized_content)
                logger.debug(f"Split document into {len(chunks)} chunks")
            except Exception as e:
                logger.error(f"Error splitting document into chunks: {str(e)}")
                raise ConnectionError(f"Failed to split document: {str(e)}")
            
            if not chunks:
                raise ValueError("No chunks generated from document")
            
            # Process each chunk with retry logic
            processed_chunks = []
            for i, chunk in enumerate(chunks):
                try:
                    processed_chunk = await self._process_chunk_with_retry(chunk, i)
                    processed_chunks.append(processed_chunk)
                except Exception as e:
                    logger.error(f"Failed to process chunk {i}: {str(e)}")
                    # Continue with other chunks instead of failing completely
                    processed_chunks.append({
                        "index": i,
                        "content": chunk,
                        "token_count": len(self.tokenizer.encode(chunk)),
                        "key_points": ["Processing failed"],
                        "error": str(e)
                    })
            
            # Generate summary with error handling
            try:
                summary = await self._generate_summary_with_retry(processed_chunks)
            except Exception as e:
                logger.error(f"Failed to generate summary: {str(e)}")
                summary = "Summary generation failed"
            
            result = {
                "chunks": processed_chunks,
                "summary": summary,
                "total_chunks": len(chunks),
                "processed_at": datetime.utcnow().isoformat(),
                "success": True
            }
            
            logger.info(f"Successfully processed document with {len(chunks)} chunks")
            return result
            
        except ValueError as e:
            logger.error(f"Invalid document input: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error processing document: {str(e)}")
            raise
    
    async def _process_chunk_with_retry(self, chunk: str, index: int, max_retries: int = 3) -> Dict[str, Any]:
        """
        Process individual text chunk with retry logic.
        
        Args:
            chunk: Text chunk to process
            index: Chunk index
            max_retries: Maximum retry attempts
            
        Returns:
            Processed chunk data
            
        Raises:
            ConnectionError: If processing fails after retries
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await self._process_chunk(chunk, index)
            except Exception as e:
                last_error = e
                logger.warning(f"Chunk {index} processing attempt {attempt + 1} failed: {str(e)}")
                
                if attempt < max_retries - 1:
                    # Exponential backoff
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
        
        # All retries failed
        logger.error(f"All processing attempts failed for chunk {index}")
        raise ConnectionError(f"Failed to process chunk {index} after {max_retries} attempts: {str(last_error)}")
    
    async def _process_chunk(self, chunk: str, index: int) -> Dict[str, Any]:
        """
        Process individual text chunk with enhanced error handling.
        
        Args:
            chunk: Text chunk to process
            index: Chunk index
            
        Returns:
            Processed chunk data
        """
        logger.debug(f"Processing chunk {index} (length: {len(chunk)})")
        
        try:
            # Validate chunk
            if not isinstance(chunk, str) or not chunk.strip():
                raise ValueError(f"Invalid chunk {index}: empty or non-string content")
            
            # Get token count with error handling
            try:
                tokens = self.tokenizer.encode(chunk)
                token_count = len(tokens)
            except Exception as e:
                logger.warning(f"Failed to tokenize chunk {index}: {str(e)}")
                token_count = len(chunk.split())  # Fallback to word count
            
            # Extract key points with error handling
            try:
                key_points = await self._extract_key_points_with_retry(chunk)
            except Exception as e:
                logger.warning(f"Failed to extract key points from chunk {index}: {str(e)}")
                key_points = ["Key point extraction failed"]
            
            return {
                "index": index,
                "content": chunk,
                "token_count": token_count,
                "key_points": key_points,
                "processed_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error processing chunk {index}: {str(e)}")
            raise
    
    async def _extract_key_points_with_retry(self, text: str, max_retries: int = 3) -> List[str]:
        """
        Extract key points with retry logic.
        
        Args:
            text: Text to extract points from
            max_retries: Maximum retry attempts
            
        Returns:
            List of key points
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await self._extract_key_points(text)
            except Exception as e:
                last_error = e
                logger.warning(f"Key point extraction attempt {attempt + 1} failed: {str(e)}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)  # Short delay between retries
        
        # All retries failed
        logger.error(f"All key point extraction attempts failed")
        return ["Key point extraction failed"]
    
    async def _extract_key_points(self, text: str) -> List[str]:
        """
        Extract key points from text with enhanced error handling.
        
        Args:
            text: Text to extract points from
            
        Returns:
            List of key points
        """
        try:
            # Sanitize text for prompt
            sanitized_text = self._sanitize_content(text[:2000])  # Limit text length
            
            prompt = f"""
            Extract the key points from this text. Return only the main points, one per line:
            
            {sanitized_text}
            """
            
            # Call LLM with timeout
            try:
                response = await asyncio.wait_for(
                    self.llm.apredict(prompt),
                    timeout=30.0  # 30 second timeout
                )
            except asyncio.TimeoutError:
                raise ConnectionError("LLM request timed out")
            
            if not response:
                return ["No key points extracted"]
            
            # Parse response
            points = [point.strip() for point in response.split('\n') if point.strip()]
            
            # Validate points
            if not points:
                return ["No key points found"]
            
            # Limit number of points
            return points[:10]  # Maximum 10 key points
            
        except Exception as e:
            logger.error(f"Error extracting key points: {str(e)}")
            raise
    
    async def _generate_summary_with_retry(self, chunks: List[Dict[str, Any]], max_retries: int = 3) -> str:
        """
        Generate summary with retry logic.
        
        Args:
            chunks: Processed chunks
            max_retries: Maximum retry attempts
            
        Returns:
            Generated summary
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await self._generate_summary(chunks)
            except Exception as e:
                last_error = e
                logger.warning(f"Summary generation attempt {attempt + 1} failed: {str(e)}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)  # Longer delay for summary generation
        
        # All retries failed
        logger.error(f"All summary generation attempts failed")
        return "Summary generation failed"
    
    async def _generate_summary(self, chunks: List[Dict[str, Any]]) -> str:
        """
        Generate overall summary from processed chunks with enhanced error handling.
        
        Args:
            chunks: List of processed chunks
            
        Returns:
            Generated summary
        """
        try:
            if not chunks:
                return "No content to summarize"
            
            # Combine key points from all chunks
            all_points = []
            for chunk in chunks:
                if isinstance(chunk, dict) and "key_points" in chunk:
                    points = chunk["key_points"]
                    if isinstance(points, list):
                        all_points.extend(points)
            
            if not all_points:
                return "No key points available for summary"
            
            # Limit points to prevent prompt overflow
            limited_points = all_points[:50]  # Maximum 50 points
            points_text = "\n".join(limited_points)
            
            # Sanitize for prompt
            sanitized_points = self._sanitize_content(points_text[:3000])  # Limit length
            
            prompt = f"""
            Synthesize these key points into a coherent summary:
            
            {sanitized_points}
            
            Provide a concise but comprehensive summary in 2-3 paragraphs.
            """
            
            # Call LLM with timeout
            try:
                summary = await asyncio.wait_for(
                    self.llm.apredict(prompt),
                    timeout=60.0  # 60 second timeout for summary
                )
            except asyncio.TimeoutError:
                raise ConnectionError("Summary generation timed out")
            
            if not summary:
                return "Summary generation failed - no response"
            
            return summary.strip()
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise

class ContentAnalyzer:
    """
    Enhanced content analyzer with comprehensive error handling, security, and observability.
    
    Features:
    - Secure content analysis and metadata extraction
    - Input validation and sanitization
    - Comprehensive error handling and retry logic
    - Structured logging and monitoring
    - Protection against injection attacks
    """
    
    def __init__(self):
        """
        Initialize content analyzer with enhanced security and error handling.
        
        Raises:
            ValueError: If initialization fails
        """
        try:
            logger.info("Initializing ContentAnalyzer with enhanced security")
            
            # Initialize LLM with error handling
            try:
                self.llm = ChatOpenAI(temperature=0)
                logger.info("ContentAnalyzer LLM client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize LLM client: {str(e)}")
                raise
            
            # Initialize tokenizer with error handling
            try:
                self.tokenizer = tiktoken.get_encoding("cl100k_base")
                logger.info("ContentAnalyzer tokenizer initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize tokenizer: {str(e)}")
                raise
            
            logger.info("ContentAnalyzer initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize ContentAnalyzer: {str(e)}")
            raise
    
    def _validate_input(self, content: str, max_length: int = 1000000) -> None:
        """
        Validate input content for security and safety.
        
        Args:
            content: Content to validate
            max_length: Maximum allowed length
            
        Raises:
            ValueError: If content is invalid
        """
        if not isinstance(content, str):
            raise ValueError("Content must be a string")
        
        if not content.strip():
            raise ValueError("Content cannot be empty")
        
        if len(content) > max_length:
            raise ValueError(f"Content too long (max {max_length} characters)")
        
        # Check for potentially dangerous content
        dangerous_patterns = [
            r'<script.*?>.*?</script>',  # Script tags
            r'javascript:',              # JavaScript protocol
            r'data:text/html',           # Data URLs
            r'vbscript:',                # VBScript
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                raise ValueError(f"Content contains potentially dangerous patterns: {pattern}")
    
    def _sanitize_content(self, content: str) -> str:
        """
        Sanitize content to prevent injection attacks.
        
        Args:
            content: Content to sanitize
            
        Returns:
            Sanitized content
        """
        # Basic XSS protection
        sanitized = content.replace('<', '&lt;').replace('>', '&gt;')
        
        # Remove null bytes and other control characters
        sanitized = ''.join(char for char in sanitized if ord(char) >= 32 or char in '\n\r\t')
        
        return sanitized.strip()
    
    async def analyze_content(self, content: str) -> Dict[str, Any]:
        """
        Analyze document content with enhanced error handling and security.
        
        Args:
            content: Document content to analyze
            
        Returns:
            Analysis results with metadata, topics, and complexity
            
        Raises:
            ValueError: If content is invalid
            ConnectionError: If analysis fails
        """
        try:
            # Input validation and sanitization
            self._validate_input(content)
            sanitized_content = self._sanitize_content(content)
            
            logger.info(f"Analyzing document content (length: {len(sanitized_content)})")
            
            # Run analysis tasks with error handling
            results = await asyncio.gather(
                self._extract_metadata_with_retry(sanitized_content),
                self._identify_topics_with_retry(sanitized_content),
                self._assess_complexity_with_retry(sanitized_content),
                return_exceptions=True
            )
            
            # Handle results with error checking
            metadata = results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])}
            topics = results[1] if not isinstance(results[1], Exception) else ["Analysis failed"]
            complexity = results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])}
            
            result = {
                "metadata": metadata,
                "topics": topics,
                "complexity": complexity,
                "analyzed_at": datetime.utcnow().isoformat(),
                "success": True
            }
            
            logger.info("Successfully analyzed document content")
            return result
            
        except ValueError as e:
            logger.error(f"Invalid content input: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error analyzing content: {str(e)}")
            raise
    
    async def _extract_metadata_with_retry(self, content: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Extract metadata with retry logic.
        
        Args:
            content: Content to analyze
            max_retries: Maximum retry attempts
            
        Returns:
            Extracted metadata
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await self._extract_metadata(content)
            except Exception as e:
                last_error = e
                logger.warning(f"Metadata extraction attempt {attempt + 1} failed: {str(e)}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
        
        logger.error(f"All metadata extraction attempts failed")
        return {"error": str(last_error)}
    
    async def _extract_metadata(self, content: str) -> Dict[str, Any]:
        """
        Extract metadata from content with enhanced error handling.
        
        Args:
            content: Content to analyze
            
        Returns:
            Extracted metadata
        """
        try:
            # Limit content for analysis
            analysis_content = content[:2000]  # First 2000 characters
            sanitized_content = self._sanitize_content(analysis_content)
            
            prompt = f"""
            Extract the following metadata from this text:
            - Document type
            - Main subject area
            - Approximate date or time period
            - Key entities mentioned
            - Language
            
            Text: {sanitized_content}
            
            Return the information in a structured format.
            """
            
            # Call LLM with timeout
            try:
                response = await asyncio.wait_for(
                    self.llm.apredict(prompt),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                raise ConnectionError("Metadata extraction timed out")
            
            if not response:
                return {"error": "No metadata extracted"}
            
            return self._parse_metadata(response)
            
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            raise
    
    async def _identify_topics_with_retry(self, content: str, max_retries: int = 3) -> List[str]:
        """
        Identify topics with retry logic.
        
        Args:
            content: Content to analyze
            max_retries: Maximum retry attempts
            
        Returns:
            Identified topics
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await self._identify_topics(content)
            except Exception as e:
                last_error = e
                logger.warning(f"Topic identification attempt {attempt + 1} failed: {str(e)}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
        
        logger.error(f"All topic identification attempts failed")
        return ["Topic identification failed"]
    
    async def _identify_topics(self, content: str) -> List[str]:
        """
        Identify main topics in content with enhanced error handling.
        
        Args:
            content: Content to analyze
            
        Returns:
            List of identified topics
        """
        try:
            # Limit content for analysis
            analysis_content = content[:2000]  # First 2000 characters
            sanitized_content = self._sanitize_content(analysis_content)
            
            prompt = f"""
            Identify the main topics discussed in this text. Return as a list, one topic per line.
            
            Text: {sanitized_content}
            """
            
            # Call LLM with timeout
            try:
                response = await asyncio.wait_for(
                    self.llm.apredict(prompt),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                raise ConnectionError("Topic identification timed out")
            
            if not response:
                return ["No topics identified"]
            
            # Parse response
            topics = [topic.strip() for topic in response.split('\n') if topic.strip()]
            
            # Validate and limit topics
            if not topics:
                return ["No topics found"]
            
            return topics[:10]  # Maximum 10 topics
            
        except Exception as e:
            logger.error(f"Error identifying topics: {str(e)}")
            raise
    
    async def _assess_complexity_with_retry(self, content: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Assess complexity with retry logic.
        
        Args:
            content: Content to analyze
            max_retries: Maximum retry attempts
            
        Returns:
            Complexity assessment
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await self._assess_complexity(content)
            except Exception as e:
                last_error = e
                logger.warning(f"Complexity assessment attempt {attempt + 1} failed: {str(e)}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
        
        logger.error(f"All complexity assessment attempts failed")
        return {"error": str(last_error)}
    
    async def _assess_complexity(self, content: str) -> Dict[str, Any]:
        """
        Assess content complexity with enhanced error handling.
        
        Args:
            content: Content to analyze
            
        Returns:
            Complexity assessment
        """
        try:
            # Count tokens with error handling
            try:
                tokens = self.tokenizer.encode(content)
                token_count = len(tokens)
            except Exception as e:
                logger.warning(f"Failed to tokenize content: {str(e)}")
                token_count = len(content.split())  # Fallback to word count
            
            # Calculate metrics
            word_count = len(content.split())
            unique_words = len(set(content.lower().split()))
            
            # Calculate complexity score
            if word_count > 0:
                vocabulary_diversity = unique_words / word_count
            else:
                vocabulary_diversity = 0
            
            # Estimate reading time (average 200 words per minute)
            estimated_reading_time = word_count / 200 if word_count > 0 else 0
            
            return {
                "token_count": token_count,
                "word_count": word_count,
                "unique_words": unique_words,
                "vocabulary_diversity": round(vocabulary_diversity, 3),
                "estimated_reading_time_minutes": round(estimated_reading_time, 1),
                "complexity_score": round(vocabulary_diversity * 100, 1)  # Scale to 0-100
            }
            
        except Exception as e:
            logger.error(f"Error assessing complexity: {str(e)}")
            raise
    
    def _parse_metadata(self, response: str) -> Dict[str, Any]:
        """
        Parse metadata from LLM response with enhanced error handling.
        
        Args:
            response: LLM response to parse
            
        Returns:
            Parsed metadata
        """
        try:
            if not response:
                return {"error": "Empty response"}
            
            lines = response.strip().split('\n')
            metadata = {}
            current_key = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith('-'):
                    # New key-value pair
                    parts = line[1:].split(':', 1)
                    if len(parts) >= 2:
                        current_key = parts[0].strip().lower().replace(' ', '_')
                        value = parts[1].strip()
                        metadata[current_key] = value
                    elif len(parts) == 1:
                        current_key = parts[0].strip().lower().replace(' ', '_')
                        metadata[current_key] = ""
                elif current_key and line:
                    # Continue previous value
                    if metadata[current_key]:
                        metadata[current_key] += ' ' + line
                    else:
                        metadata[current_key] = line
            
            # Clean up empty values
            metadata = {k: v for k, v in metadata.items() if v}
            
            return metadata if metadata else {"error": "No metadata parsed"}
            
        except Exception as e:
            logger.error(f"Error parsing metadata: {str(e)}")
            return {"error": f"Failed to parse metadata: {str(e)}"}