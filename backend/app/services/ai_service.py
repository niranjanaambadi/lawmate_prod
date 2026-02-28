"""
AI Service using AWS Bedrock (Claude)
"""
import boto3
import json
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import UUID
import pypdf
from io import BytesIO

from app.db.models import AIAnalysis, Document, Case
from app.core.config import settings

# Simple logger (replace with app.core.logger if it exists)
import logging
logger = logging.getLogger(__name__)


class AIService:
    """
    Service layer for AI analysis using AWS Bedrock Claude
    """
    
    def __init__(self):
        self.bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        self.s3_client = boto3.client(
            's3',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        self.model_id = settings.BEDROCK_MODEL_ID
    
    def analyze_case(self, case_id: str, advocate_id: str, db: Session):
        """
        Main entry point for AI case analysis
        Called as background task after case sync
        """
        try:
            logger.info(f"Starting AI analysis for case {case_id}")
            
            # Get or create analysis record
            analysis = db.query(AIAnalysis).filter(
                AIAnalysis.case_id == case_id
            ).first()
            
            if not analysis:
                analysis = AIAnalysis(
                    case_id=case_id,
                    advocate_id=advocate_id,
                    status="processing",
                    model_version=self.model_id
                )
                db.add(analysis)
            else:
                analysis.status = "processing"
            
            db.commit()
            
            # Get case and documents
            case = db.query(Case).filter(Case.id == case_id).first()
            
            documents = db.query(Document).filter(
                Document.case_id == case_id,
                Document.upload_status == "completed"
            ).limit(5).all()  # Analyze first 5 docs max
            
            if not documents:
                analysis.status = "failed"
                analysis.error_message = "No documents available"
                db.commit()
                return analysis
            
            # Extract text from documents
            extracted_text = self._extract_text_from_documents(documents)
            
            if not extracted_text or len(extracted_text.strip()) < 50:
                analysis.status = "failed"
                analysis.error_message = "Insufficient text extracted"
                db.commit()
                return analysis
            
            # Perform AI analysis
            start_time = datetime.utcnow()
            analysis_result = self._analyze_with_claude(extracted_text, case)
            end_time = datetime.utcnow()
            
            # Update analysis record
            analysis.status = "completed"
            analysis.analysis = analysis_result
            analysis.urgency_level = analysis_result.get("urgency_level", "medium")
            analysis.case_summary = analysis_result.get("case_summary", "")
            analysis.processed_at = end_time
            analysis.processing_time_seconds = int((end_time - start_time).total_seconds())
            analysis.token_count = analysis_result.get("_meta", {}).get("token_count", 0)
            
            db.commit()
            
            logger.info(f"AI analysis completed for case {case_id}")
            return analysis
            
        except Exception as e:
            logger.error(f"AI analysis failed for case {case_id}: {str(e)}")
            
            if analysis:
                analysis.status = "failed"
                analysis.error_message = str(e)
                analysis.retry_count += 1
                db.commit()
            
            return None
    
    def _extract_text_from_documents(self, documents: list) -> str:
        """
        Extract text from PDF documents
        """
        all_text = []
        
        for doc in documents:
            try:
                # Download PDF from S3
                response = self.s3_client.get_object(
                    Bucket=doc.s3_bucket,
                    Key=doc.s3_key
                )
                pdf_bytes = response['Body'].read()
                
                # Extract text using pypdf
                text = self._extract_with_pypdf(pdf_bytes)
                
                if text and len(text.strip()) > 50:
                    all_text.append(f"--- Document: {doc.title} ---\n{text}\n")
                
            except Exception as e:
                logger.error(f"Failed to extract text from {doc.s3_key}: {str(e)}")
                continue
        
        return "\n\n".join(all_text)
    
    def _extract_with_pypdf(self, pdf_bytes: bytes) -> str:
        """
        Extract text using pypdf
        """
        try:
            pdf_reader = pypdf.PdfReader(BytesIO(pdf_bytes))
            text = ""
            
            # Extract from first 10 pages max
            for page in pdf_reader.pages[:10]:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            
            return text
            
        except Exception as e:
            logger.error(f"pypdf extraction failed: {str(e)}")
            return ""
    
    def _analyze_with_claude(self, document_text: str, case: Case) -> Dict[str, Any]:
        """
        Analyze document using Claude 3.5 Sonnet
        """
        prompt = self._build_analysis_prompt(document_text, case)
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4096,
                    "temperature": 0.3,
                    "messages": [{
                        "role": "user",
                        "content": prompt
                    }]
                })
            )
            
            response_body = json.loads(response['body'].read())
            analysis_text = response_body['content'][0]['text']
            
            # Parse JSON from Claude's response
            try:
                analysis_json = json.loads(analysis_text)
            except json.JSONDecodeError:
                # Extract JSON from markdown code blocks
                import re
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', analysis_text, re.DOTALL)
                if not json_match:
                    json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
                
                if json_match:
                    analysis_json = json.loads(json_match.group(1) if json_match.lastindex else json_match.group())
                else:
                    # Fallback structure
                    analysis_json = {
                        "case_summary": analysis_text[:500],
                        "urgency_level": "medium",
                        "key_legal_issues": [],
                        "deadline_reminders": []
                    }
            
            # Add metadata
            analysis_json["_meta"] = {
                "model": self.model_id,
                "token_count": response_body.get('usage', {}).get('input_tokens', 0) + 
                               response_body.get('usage', {}).get('output_tokens', 0),
                "analyzed_at": datetime.utcnow().isoformat()
            }
            
            return analysis_json
            
        except Exception as e:
            logger.error(f"Claude analysis failed: {str(e)}")
            # Return minimal structure on failure
            return {
                "case_summary": "Analysis failed",
                "urgency_level": "medium",
                "error": str(e)
            }
    
    def _build_analysis_prompt(self, document_text: str, case: Case) -> str:
        """
        Build the analysis prompt for Claude
        """
        prompt = f"""You are a legal AI assistant for Kerala High Court advocates. 
Analyze the following case document and provide a structured analysis.

**Case Information:**
- Case Number: {case.case_number or case.efiling_number}
- Case Type: {case.case_type}
- Filing Date: {case.efiling_date}
- Parties: {case.petitioner_name} vs {case.respondent_name}

**Document Content (first 50,000 characters):**
{document_text[:50000]}

**Analysis Requirements:**
Provide a JSON response with the following structure:

{{
  "case_type_classification": "Detailed classification",
  "key_legal_issues": ["List of main legal issues"],
  "relevant_statutes": ["List of applicable statutes"],
  "precedent_cases": [
    {{
      "name": "Case name",
      "citation": "Citation",
      "relevance": "Brief explanation"
    }}
  ],
  "action_items": ["List of specific actions"],
  "urgency_level": "high/medium/low/critical",
  "deadline_reminders": [
    {{
      "task": "Description",
      "due_date": "YYYY-MM-DD",
      "priority": "critical/high/medium/low"
    }}
  ],
  "case_summary": "2-3 line summary for dashboard",
  "legal_strategy_recommendations": ["Strategic recommendations"],
  "potential_challenges": ["Potential legal challenges"],
  "success_probability": "high/medium/low with reasoning"
}}

Focus on Kerala High Court practices. Be precise and actionable.
Respond with ONLY the JSON, no additional text.
"""
        return prompt
    
    def chat_with_document(
        self,
        document_id: str,
        message: str,
        conversation_history: list,
        db: Session
    ) -> str:
        """
        Chat with a specific document using Claude
        """
        try:
            # Get document
            document = db.query(Document).filter(Document.id == document_id).first()
            
            if not document:
                return "Document not found"
            
            # Download and extract text
            response = self.s3_client.get_object(
                Bucket=document.s3_bucket,
                Key=document.s3_key
            )
            pdf_bytes = response['Body'].read()
            document_text = self._extract_with_pypdf(pdf_bytes)
            
            if not document_text or len(document_text.strip()) < 50:
                return "Could not extract text from document"
            
            # Build conversation
            messages = []
            
            # System context
            context_message = {
                "role": "user",
                "content": f"""You are analyzing a legal document titled "{document.title}".

Document content (first 30,000 characters):
{document_text[:30000]}

Answer questions about this document accurately and concisely. 
If asked about information not in the document, say so clearly."""
            }
            
            system_response = {
                "role": "assistant",
                "content": "I've read the document. I'm ready to answer your questions about it."
            }
            
            messages.append(context_message)
            messages.append(system_response)
            
            # Add conversation history
            for msg in conversation_history[-5:]:  # Last 5 messages
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Add current message
            messages.append({
                "role": "user",
                "content": message
            })
            
            # Call Claude
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 2048,
                    "temperature": 0.5,
                    "messages": messages
                })
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text']
            
        except Exception as e:
            logger.error(f"Document chat failed: {str(e)}")
            return f"Sorry, I encountered an error: {str(e)}"

    def extract_document_bedrock_pdf(
        self,
        pdf_bytes: bytes,
        filename: str = "document.pdf",
        use_visual_mode: bool = True,
    ) -> Dict[str, Any]:
        """
        Extract text from a PDF using Amazon Bedrock's native PDF support (Converse API).
        See: https://platform.claude.com/docs/en/build-with-claude/pdf-support

        Two document processing modes (Bedrock Converse API):
        - use_visual_mode=False: Text extraction only (~1k tokens/3 pages). Faster, cheaper.
        - use_visual_mode=True: Full visual understanding (charts, images, layout). Requires
          citations enabled (~7k tokens/3 pages).

        Returns: { "extractedText", "pageCount", "processingMode": "text_only"|"full_visual" }
        """
        page_count = 0
        try:
            pdf_reader = pypdf.PdfReader(BytesIO(pdf_bytes))
            page_count = len(pdf_reader.pages)
        except Exception:
            page_count = 1

        prompt = (
            "Extract all text from this document. Preserve paragraphs, headings, and list structure. "
            "For legal documents also identify: parties, dates, case numbers, court, and key facts. "
            "Output only the extracted text, no commentary or meta-description."
        )

        try:
            # Converse API with document block (native PDF support)
            # citations.enabled=True => full visual; False => text extraction only
            conversation = [
                {
                    "role": "user",
                    "content": [
                        {
                            "document": {
                                "format": "pdf",
                                "name": filename[:200],
                                "source": {"bytes": pdf_bytes},
                                "citations": {"enabled": use_visual_mode},
                            }
                        },
                        {"text": prompt},
                    ],
                }
            ]

            response = self.bedrock_client.converse(
                modelId=self.model_id,
                messages=conversation,
                inferenceConfig={"maxTokens": 4096, "temperature": 0.0},
            )

            # Response: output.message.content is list of content blocks
            output = response.get("output", {})
            message = output.get("message", {})
            content_blocks = message.get("content", [])

            extracted = []
            for block in content_blocks:
                if "text" in block:
                    extracted.append(block["text"])
                # Citations block: use its "content" text if present
                if "citations" in block:
                    cite_content = block.get("citations", {}).get("content")
                    if cite_content:
                        extracted.append(cite_content)

            combined = "\n\n".join(extracted).strip() if extracted else ""
            return {
                "extractedText": combined or "No text could be extracted from the document.",
                "pageCount": page_count,
                "processingMode": "full_visual" if use_visual_mode else "text_only",
            }
        except Exception as e:
            logger.exception("Bedrock Converse PDF extraction failed")
            fallback = self._extract_with_pypdf(pdf_bytes)
            return {
                "extractedText": (fallback or "").strip()
                or f"Extraction failed: {str(e)}",
                "pageCount": page_count,
                "processingMode": "text_only",
            }

    def chat_about_document(
        self,
        extracted_text: str,
        question: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Answer user questions about the extracted document text using Bedrock Converse (text only).
        Uses the provided extracted text as context; no PDF re-upload.
        """
        if not (extracted_text or extracted_text.strip()):
            return "There is no document content to answer from. Please extract the document first."
        if not (question or question.strip()):
            return "Please ask a question about the document."

        history = conversation_history or []
        # Build messages for InvokeModel (Anthropic Claude messages format). Content as array of blocks.
        messages = []
        for turn in history:
            role = turn.get("role")
            content = turn.get("content") or turn.get("text") or ""
            if role and content and role in ("user", "assistant"):
                messages.append({"role": role, "content": [{"type": "text", "text": content}]})

        doc_excerpt = (extracted_text.strip()[:120000] + "...") if len(extracted_text) > 120000 else extracted_text.strip()
        user_content = (
            "Use the following document content to answer the user's question. "
            "If the answer is not in the document, say so. Answer concisely and accurately.\n\n"
            "--- Document content ---\n"
            f"{doc_excerpt}\n\n"
            "--- User question ---\n"
            f"{question.strip()}"
        )
        messages.append({"role": "user", "content": [{"type": "text", "text": user_content}]})

        model_id = settings.BEDROCK_MODEL_ID
        try:
            # Use invoke_model (works with boto3 1.34.x); converse() requires boto3 >= 1.35.8
            response = self.bedrock_client.invoke_model(
                modelId=model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 2048,
                    "temperature": 0.2,
                    "messages": messages,
                }),
            )
            response_body = json.loads(response["body"].read())
            content_list = response_body.get("content", [])
            if content_list and "text" in content_list[0]:
                return content_list[0]["text"].strip()
            return "I couldn't generate a response. Please try again."
        except Exception as e:
            logger.exception("Document chat failed")
            return f"Sorry, I encountered an error: {str(e)}"


# Singleton instance
ai_service = AIService()