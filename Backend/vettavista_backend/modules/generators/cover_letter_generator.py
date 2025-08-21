import logging
import os
import shutil
from datetime import datetime

from pylatex import Document, Package, NoEscape
from pylatex.utils import escape_latex

from vettavista_backend.config import personals, resume

logger = logging.getLogger(__name__)

class CoverLetterDocument(Document):
    """Custom document class for cover letter generation."""
    def __init__(self):
        super().__init__(documentclass='article', document_options=['11pt', 'a4paper'])
        
        # Clear all default packages
        self.packages.clear()
        
        # Add packages in exact order from template
        self.packages.add(Package('latexsym'))
        self.packages.add(Package('fullpage', options='empty'))
        self.packages.add(Package('titlesec'))
        self.packages.add(Package('marvosym'))
        self.packages.add(Package('color', options='usenames,dvipsnames'))
        self.packages.add(Package('verbatim'))
        self.packages.add(Package('hyperref'))
        self.packages.add(Package('fancyhdr'))
        self.packages.add(Package('multicol'))
        self.packages.add(Package('csquotes'))
        self.packages.add(Package('tabularx'))
        self.packages.add(Package('moresize', options='11pt'))
        self.packages.add(Package('setspace'))
        self.packages.add(Package('fontspec'))
        self.packages.add(Package('enumitem', options='inline'))
        self.packages.add(Package('ragged2e'))
        self.packages.add(Package('anyfontsize'))
        self.packages.add(Package('geometry', options='margin=1cm'))
        
        # Document setup
        self.preamble.append(NoEscape(r'\hypersetup{colorlinks=true,urlcolor=black}'))
        self.preamble.append(NoEscape(r'\setmainfont[BoldFont=SourceSansPro-SemiBold.ttf,ItalicFont=SourceSansPro-RegularIt.ttf]{SourceSansPro-Regular.ttf}'))
        self.preamble.append(NoEscape(r'\pagestyle{fancy}\fancyhf{}\fancyfoot{}'))
        self.preamble.append(NoEscape(r'\setlength{\footskip}{5pt}'))
        self.preamble.append(NoEscape(r'\renewcommand{\headrulewidth}{0pt}\renewcommand{\footrulewidth}{0pt}'))
        self.preamble.append(NoEscape(r'\urlstyle{same}'))
        self.preamble.append(NoEscape(r'\raggedbottom\raggedright'))
        self.preamble.append(NoEscape(r'\setlength{\tabcolsep}{0in}'))
        self.preamble.append(NoEscape(r'\hyphenpenalty=10000'))
        self.preamble.append(NoEscape(r'\exhyphenpenalty=10000'))
        self.preamble.append(NoEscape(r'\sloppy'))
        self.preamble.append(NoEscape(r'\raggedright'))
        self.preamble.append(NoEscape(r'\definecolor{UI_blue}{RGB}{32, 64, 151}'))
        self.preamble.append(NoEscape(r'\definecolor{HF_color}{RGB}{179, 179, 179}'))


class CoverLetterGenerator:
    """Generator for cover letter PDFs."""
    def __init__(self, output_dir: str = "generated"):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Copy required font files
        current_dir = os.path.dirname(os.path.abspath(__file__))
        font_files = [
            'SourceSansPro-Regular.ttf',
            'SourceSansPro-RegularIt.ttf',
            'SourceSansPro-SemiBold.ttf'
        ]
        for font_file in font_files:
            src = os.path.join(current_dir, font_file)
            dst = os.path.join(output_dir, font_file)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

    def _setup_document(self) -> CoverLetterDocument:
        """Set up a cover letter document with header and basic structure."""
        doc = CoverLetterDocument()
        
        # Header section
        doc.append(NoEscape(r'\begin{center}'))
        
        # Contact info
        doc.append(NoEscape(r'\begin{minipage}[b]{0.25\textwidth}'))
        # doc.append(NoEscape(fr'\large {escape_latex(personals.phone)} \\'))
        doc.append(NoEscape(fr'\large \href{{mailto:{personals.email}}}{{{escape_latex(personals.email)}}}'))
        doc.append(NoEscape(r'\end{minipage}%'))
        
        # Name
        doc.append(NoEscape(r'\begin{minipage}[b]{0.5\textwidth}\centering'))
        full_name = f"{personals.first_name} {personals.middle_name} {personals.last_name}".strip()
        doc.append(NoEscape(fr'{{\Huge {escape_latex(full_name)}}} \\\vspace{{0.1cm}}'))
        doc.append(NoEscape(r'\end{minipage}%'))
        
        # Links
        doc.append(NoEscape(r'\begin{minipage}[b]{0.25\textwidth}\flushright \large'))
        linkedin_id = resume.linkedIn.split('/')[-1]
        doc.append(NoEscape(fr'{{\href{{{NoEscape(resume.linkedIn)}}}{{linkedin.com/{linkedin_id}}} }} \\'))
        doc.append(NoEscape(fr'\href{{{NoEscape(resume.website)}}}{{{escape_latex(resume.website.replace("https://", ""))}}}'))
        doc.append(NoEscape(r'\end{minipage}'))
        
        # Blue line and title
        doc.append(NoEscape(r'\vspace{-0.15cm}' + '\n'))
        doc.append(NoEscape(r'{\color{UI_blue}\hrulefill}' + '\n'))
        doc.append(NoEscape(r'\end{center}' + '\n'))
        
        # Cover letter header
        doc.append(NoEscape(r'\justify\setlength{\parindent}{0pt}\setlength{\parskip}{12pt}\vspace{0.2cm}'))
        doc.append(NoEscape(r'\begin{center}{\color{UI_blue} \Large{COVER LETTER}}\end{center}'))
        
        return doc

    def generate_body(self, company_name: str, content: str) -> str:
        """Generate complete cover letter text with header and signature."""
        full_name = f"{personals.first_name} {personals.middle_name} {personals.last_name}".strip()
        today = datetime.now().strftime("%B %d, %Y")
        
        letter_text = f"""Date: {today}

Dear Hiring Team at {company_name},

{content.strip()}

Sincerely,

{full_name}"""
        return letter_text

    def generate_pdf_from_text(self, text: str, output_filename: str = "generated_cover_letter") -> str:
        """Generate a PDF file from plain text content."""
        try:
            doc = self._setup_document()
            doc.append(NoEscape(escape_latex(text)))
            
            # Generate PDF
            output_path = os.path.join(self.output_dir, output_filename)
            doc.generate_pdf(
                output_path,
                clean_tex=False,
                compiler='xelatex',
                compiler_args=['-interaction=nonstopmode']
            )
            logger.info(f"Generated cover letter PDF from text: {output_path}.pdf")
            return output_path + '.pdf'
            
        except Exception as e:
            logger.error(f"Failed to generate PDF from text: {str(e)}")
            raise

    # Keep this for testing only
    def generate_cover_letter(self, company_name: str, content: str, output_filename: str = "generated_cover_letter") -> str:
        """Generate a cover letter PDF with the given content. For testing only."""
        try:
            letter_text = self.generate_body(company_name, content)
            return self.generate_pdf_from_text(letter_text, output_filename)
            
        except Exception as e:
            logger.error(f"Failed to generate cover letter: {str(e)}")
            raise

    def generate_latex(self, company_name: str, content: str) -> str:
        """Generate LaTeX content without creating a PDF."""
        try:
            doc = self._setup_document()
            doc.append(NoEscape(escape_latex(self.generate_body(company_name, content))))
            return doc.dumps()
            
        except Exception as e:
            logger.error(f"Failed to generate LaTeX content: {str(e)}")
            raise


if __name__ == "__main__":
    generator = CoverLetterGenerator()
    
    # Test data
    company_name = "Example Corp"
    content = """I am writing to express my strong interest in the Software Engineer position at Example Corp. With my background in computer science and experience in full-stack development, I believe I would be a valuable addition to your team.

Thank you for considering my application. I look forward to discussing how I can contribute to Example Corp's continued success."""
    
    # Test normal cover letter generation
    # generator.generate_cover_letter(company_name, content)
    
    # Test latex generation and PDF from latex
    latex_content = generator.generate_body(company_name, content)
    generator.generate_pdf_from_text(latex_content, "from_latex_test")
    
    print("Generated both PDFs - check the output directory") 