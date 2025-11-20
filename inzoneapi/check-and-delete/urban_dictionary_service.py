# """
# Urban Dictionary Service for content moderation
# Checks slang terms and offensive language using Urban Dictionary API
# """

# import requests
# import re
# import logging
# from typing import Dict, Optional

# logger = logging.getLogger(__name__)

# class UrbanDictionaryService:
#     def __init__(self):
#         self.base_url = "https://api.urbandictionary.com/v0"
        
#     def check_slang_terms(self, text: str) -> Dict:
#         """Check for urban dictionary slang terms in text"""
#         try:
#             words = re.findall(r'\b\w+\b', text.lower())
#             flagged_terms = []
#             explanations = []
            
#             for word in words:
#                 if len(word) > 2:  # Skip very short words to avoid API spam
#                     definition = self.get_definition(word)
#                     if definition and self.is_negative_slang(definition):
#                         flagged_terms.append(word)
#                         explanations.append({
#                             "term": word,
#                             "definition": definition["definition"][:200] + "..." if len(definition["definition"]) > 200 else definition["definition"]
#                         })
            
#             return {
#                 "flagged_terms": flagged_terms,
#                 "explanations": explanations,
#                 "has_negative_slang": len(flagged_terms) > 0
#             }
#         except Exception as e:
#             logger.error(f"Urban Dictionary check failed: {e}")
#             return {"flagged_terms": [], "explanations": [], "has_negative_slang": False}
    
#     def get_definition(self, term: str) -> Optional[Dict]:
#         """Get definition from Urban Dictionary API"""
#         try:
#             response = requests.get(
#                 f"{self.base_url}/define",
#                 params={"term": term},
#                 timeout=3
#             )
#             if response.status_code == 200:
#                 data = response.json()
#                 if data.get("list") and len(data["list"]) > 0:
#                     return data["list"][0]  # Return the top definition
#             return None
#         except Exception:
#             return None
    
#     def is_negative_slang(self, definition_data: Dict) -> bool:
#         """Check if the slang term has negative connotations"""
#         definition = definition_data.get("definition", "").lower()
#         example = definition_data.get("example", "").lower()
        
#         # Negative keywords to check for
#         negative_keywords = [
#             "hate", "stupid", "idiot", "kill", "die", "death", "murder", 
#             "violence", "abuse", "racist", "sexist", "offensive", "insult",
#             "harassment", "bullying", "threat", "harmful", "toxic", "derogatory",
#             "slur", "discrimination", "degrading", "vulgar", "obscene"
#         ]
        
#         combined_text = f"{definition} {example}"
#         return any(keyword in combined_text for keyword in negative_keywords)
