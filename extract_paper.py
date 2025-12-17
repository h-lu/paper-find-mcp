
import sys
import os

try:
    import pypdf
except ImportError:
    try:
        import PyPDF2 as pypdf
    except ImportError:
        print("Error: neither pypdf nor PyPDF2 is installed.")
        sys.exit(1)

def extract_content(pdf_path):
    try:
        reader = pypdf.PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        
        # Simple heuristic extraction
        total_len = len(text)
        print(f"Total characters: {total_len}")
        
        print("--- BEGIN ABSTRACT & INTRO ---")
        # First 15% or 4000 chars
        print(text[:5000])
        print("--- END ABSTRACT & INTRO ---")
        
        print("\n\n")
        
        print("--- BEGIN CONCLUSION & REFS ---")
        # Last 20% or 8000 chars
        start_idx = max(0, total_len - 8000)
        print(text[start_idx:])
        print("--- END CONCLUSION & REFS ---")

    except Exception as e:
        print(f"Error reading PDF: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_paper.py <pdf_path>")
        sys.exit(1)
    
    extract_content(sys.argv[1])
