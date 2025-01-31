import csv
import json
from pathlib import Path
from typing import List, Dict
import aiofiles
from datetime import datetime

class CSVHandler:
    def __init__(self):
        self.output_dir = Path("static/reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_filename(self) -> str:
        """Generate a unique filename for the CSV report"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"email_analysis_{timestamp}.csv"

    async def create_analysis_csv(self, emails: List[str], analysis_results: List[Dict], search_terms: List[str]) -> str:
        """
        Create a CSV file with email analysis results
        Returns the path to the generated CSV file
        """
        filename = self.generate_filename()
        filepath = self.output_dir / filename

        # Prepare headers
        headers = ["Subject", "Email Body", "Terms Found"] + [f"{term} - References" for term in search_terms]

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=headers)
                writer.writeheader()

                for email, analysis in zip(emails, analysis_results):
                    # Parse the JSON string result
                    result = json.loads(analysis)
                    
                    # Prepare row data
                    row = {
                        "Subject": result.get("subject", ""),
                        "Email Body": result["original_email"],
                        "Terms Found": ", ".join(result["terms_found"])
                    }
                    
                    # Add semantic matches for each term
                    for term in search_terms:
                        matches = result["semantic_matches"].get(term, [])
                        references = []
                        for match in matches:
                            references.append(
                                f"Location: {match['location']}\n"
                                f"Text: {match['text']}\n"
                                f"Explanation: {match['explanation']}"
                            )
                        row[f"{term} - References"] = "\n\n".join(references) if references else "No semantic matches found"
                    
                    writer.writerow(row)

            return str(filepath.relative_to(Path("static")))

        except Exception as e:
            print(f"Error creating CSV: {str(e)}")
            raise 