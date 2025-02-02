from openai import AsyncOpenAI
import os
import json
from typing import List, Dict
from termcolor import colored
from prompts import EMAIL_ANALYSIS_SYSTEM_PROMPT, EMAIL_SUMMARY_SYSTEM_PROMPT

from dotenv import load_dotenv  
load_dotenv()

class LLMService:
    def __init__(self):
        self.client = AsyncOpenAI()
        self.MODEL = "gpt-4o"  # Using the specified model

    def extract_email_content(self, email_raw: str) -> Dict[str, str]:
        """Extract subject and body from email, removing headers"""
        try:
            # Split email into headers and body
            parts = email_raw.split('\n\n', 1)
            headers = parts[0]
            body = parts[1] if len(parts) > 1 else ""

            # Extract subject from headers
            subject = ""
            for line in headers.split('\n'):
                if line.lower().startswith('subject:'):
                    subject = line[8:].strip()
                    break

            return {
                "subject": subject,
                "body": body.strip()
            }
        except Exception as e:
            print(colored(f"Error extracting email content: {str(e)}", "red"))
            return {
                "subject": "",
                "body": email_raw  # Fallback to using entire content
            }

    async def analyze_email_content(self, email_content: str, search_terms: List[str]) -> dict:
        """Analyze email content for semantic matches with search terms"""
        try:
            system_prompt = """You are an expert email analyzer with deep understanding of business context and semantic meaning.
Your task is to analyze emails and find relevant content based on search terms, considering:

1. Semantic Relevance: Look for content that matches the meaning and intent of search terms, not just exact matches
2. Context Understanding: Consider the broader context of discussions and implied meanings
3. Business Intelligence: Identify business-relevant information related to the search terms
4. Key Information: Extract important details even if they use different wording than the search terms
5. Related Concepts: Include relevant content that uses synonyms or related business concepts
6. Indirect References: Capture indirect mentions and implied connections to the search terms

For each search term:
- Find ALL relevant content, including semantic matches and contextually related information
- Include surrounding context to ensure the meaning is clear
- Consider business implications and relationships
- Look for both explicit and implicit references
- Consider industry-specific terminology and jargon

Return a structured analysis with:
1. Semantic matches for each term (with context)
2. Overall relevance score (0-100)
3. Key insights found
4. Important context that might not directly match but is relevant"""

            prompt = f"""Analyze this email content for the following search terms: {', '.join(search_terms)}

Email Content:
{email_content}

Provide a detailed analysis in JSON format with the following structure:
{{
    "semantic_matches": {{
        "term": [
            {{
                "text": "relevant text snippet",
                "context": "surrounding context",
                "relevance": "explanation of relevance"
            }}
        ]
    }},
    "overall_relevance_score": number,
    "key_insights": [
        "insight 1",
        "insight 2"
    ],
    "important_context": [
        "context 1",
        "context 2"
    ]
}}"""

            completion = await self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )

            return completion.choices[0].message.content

        except Exception as e:
            print(colored(f"Error in analyze_email_content: {str(e)}", "red"))
            raise

    async def generate_summary(self, all_emails: List[str], search_terms: List[str]) -> str:
        """Generate a summary of all emails focusing on semantic matches to search terms"""
        try:
            system_prompt = EMAIL_SUMMARY_SYSTEM_PROMPT.format(terms=', '.join(search_terms))
            
            # Process emails to extract subjects and bodies
            processed_emails = [self.extract_email_content(email) for email in all_emails]
            formatted_emails = [
                f"Subject: {email['subject']}\n\nBody:\n{email['body']}"
                for email in processed_emails
            ]
            
            user_prompt = f"Generate a semantic analysis summary for these emails:\n\n" + "\n---\n".join(formatted_emails)
            
            completion = await self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            return completion.choices[0].message.content.strip()
            
        except Exception as e:
            print(colored(f"Error in LLM summary generation: {str(e)}", "red"))
            raise 