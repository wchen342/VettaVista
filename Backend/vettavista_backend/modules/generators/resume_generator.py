import os
import shutil
from datetime import datetime

from pylatex import Document, Package, NoEscape, Itemize
from pylatex.base_classes import Environment, CommandBase
from pylatex.utils import escape_latex, italic, bold

from vettavista_backend.config import personals, resume, ResumeModel


def _format_date(date: datetime) -> str:
    """Format a date as YYYY-MM or 'Present'."""
    if date == datetime.max:
        return "Present"
    return date.strftime("%Y-%m")

class NameCommand(CommandBase):
    """Command for the name in resume."""
    _latex_name = 'name'

class AddressCommand(CommandBase):
    """Command for address blocks in resume."""
    _latex_name = 'address'

class HrefCommand(CommandBase):
    """Command for hyperlinks."""
    _latex_name = 'href'
    packages = [Package('hyperref')]

class RSection(Environment):
    """Environment for resume sections."""
    _latex_name = 'rSection'

class ResumeTabular(Environment):
    """Tabular environment with resume-specific format."""
    _latex_name = 'tabular'
    
    def __init__(self):
        super().__init__()
        self.arguments = NoEscape('@{} >{\\bfseries}l @{\\hspace{6ex}} p{0.7\\linewidth}')

class ResumeDocument(Document):
    """Custom document class for resume generation."""
    def __init__(self):
        super().__init__(documentclass='resume')
        self.packages.append(Package('geometry'))
        self.packages.append(Package('setspace'))

        # Set margins and spacing
        self.preamble.append(NoEscape(r'\geometry{margin=0.4in}'))
        self.preamble.append(NoEscape(r'\addtolength{\parskip}{-0.3em}'))
        self.preamble.append(NoEscape(r'\setstretch{0.85}'))

class ResumeGenerator:
    def __init__(self, output_dir: str = "generated"):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Copy resume.cls to output directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.cls_file = os.path.join(current_dir, 'resume.cls')
        shutil.copy2(self.cls_file, os.path.join(output_dir, 'resume.cls'))

    def _setup_document(self) -> ResumeDocument:
        """Set up a resume document with header and contact information."""
        doc = ResumeDocument()

        # Add name
        full_name = f"{personals.first_name} {personals.middle_name} {personals.last_name}".strip()
        doc.preamble.append(NameCommand(arguments=escape_latex(full_name)))

        # First address block
        doc.preamble.append(AddressCommand(arguments=NoEscape(
            # f"{escape_latex(personals.phone)} \\\\ {escape_latex(personals.current_city)}"
            f"{escape_latex(personals.current_city)}"
        )))

        # Second address block with links
        email_href = HrefCommand(arguments=[f'mailto:{personals.email}', escape_latex(personals.email)])
        linkedin_href = HrefCommand(arguments=[
            NoEscape(resume.linkedIn),
            escape_latex(f'linkedin.com/in/{resume.linkedIn.split("/")[-1]}')
        ])
        website_href = HrefCommand(arguments=[
            resume.website,
            escape_latex(resume.website.replace('https://', ''))
        ])
        
        doc.preamble.append(AddressCommand(arguments=NoEscape(
            f"{email_href.dumps()} \\\\ {linkedin_href.dumps()} \\\\ {website_href.dumps()}"
        )))

        return doc

    def _add_skills(self, doc: ResumeDocument, resume_model: ResumeModel):
        """Add the skills section to the document."""
        doc.append(NoEscape('\n%--------------------------------------------------------------------------------'))
        doc.append(NoEscape('% TECHNICAL STRENGTHS'))
        doc.append(NoEscape('%--------------------------------------------------------------------------------'))
        with doc.create(RSection(arguments='SKILLS')) as section:
            section.append(NoEscape('\n'))
            with section.create(ResumeTabular()) as tabular:
                for category, items in resume_model.skills.items():
                    cat_name = escape_latex(category.replace('_', ' ')).title()
                    items_str = ', '.join(escape_latex(item) for item in items)
                    tabular.append(NoEscape(f"\t{cat_name} & {items_str} \\\\"))

    def _add_experience(self, doc: ResumeDocument, resume_model: ResumeModel):
        """Add the experience section to the document."""
        doc.append(NoEscape('\n%--------------------------------------------------------------------------------'))
        doc.append(NoEscape('% EXPERIENCE'))
        doc.append(NoEscape('%--------------------------------------------------------------------------------'))
        with doc.create(RSection(arguments='EXPERIENCE')) as section:
            first = True
            for exp in resume_model.experience:
                if not first:
                    section.append(NoEscape('\n\n\smallskip'))
                else:
                    section.append(NoEscape('\n'))
                first = False

                # Title and date
                section.append(NoEscape(f"\t{bold(escape_latex(exp.title))} \\hfill {_format_date(exp.start)} - {_format_date(exp.end)}\\\\"))
                section.append(NoEscape(f"\t{escape_latex(exp.organization)} \\hfill {italic(escape_latex(exp.location))}"))

                # Details
                with section.create(Itemize()) as itemize:
                    itemize.append(NoEscape('\t\\setlength{\\itemsep}{0pt}'))
                    for detail in exp.details:
                        itemize.add_item(NoEscape(f"\t{escape_latex(detail)}"))

    def _add_projects(self, doc: ResumeDocument, resume_model: ResumeModel):
        """Add the projects section to the document."""
        doc.append(NoEscape('\n%--------------------------------------------------------------------------------'))
        doc.append(NoEscape('% PROJECTS'))
        doc.append(NoEscape('%--------------------------------------------------------------------------------'))
        with doc.create(RSection(arguments='PROJECTS')) as section:
            section.append(NoEscape(f"\t{bold('Open Source Contributions')}"))
            with section.create(Itemize()) as itemize:
                itemize.append(NoEscape('\t\\setlength{\\itemsep}{0pt}'))
                for detail in resume_model.projects[0].details:
                    itemize.add_item(NoEscape(f"\t{escape_latex(detail)}"))

    def _add_education(self, doc: ResumeDocument):
        """Add the education section to the document."""
        doc.append(NoEscape('\n%--------------------------------------------------------------------------------'))
        doc.append(NoEscape('% EDUCATION'))
        doc.append(NoEscape('%--------------------------------------------------------------------------------'))
        with doc.create(RSection(arguments='Education')) as section:
            first = True
            for edu in resume.educations:
                if not first:
                    section.append(NoEscape(r'\smallskip'))
                first = False

                # Degree and university with years
                start_year = edu.start.year
                grad_year = edu.graduation.year

                section.append(NoEscape(
                    f"\t{{{bold(escape_latex(edu.degree))}}}, {escape_latex(edu.university)} \\hfill {{{start_year} - {grad_year}}}\\\\"))

                # Extra information if available
                if hasattr(edu, 'extra'):
                    section.append(NoEscape(f"\t{escape_latex(edu.extra)}\n\n"))

    def _add_all_sections(self, doc: ResumeDocument, resume_model: ResumeModel) -> None:
        """Add all resume sections to the document."""
        self._add_skills(doc, resume_model)
        self._add_experience(doc, resume_model)
        self._add_projects(doc, resume_model)
        self._add_education(doc)

    def generate_resume(self, resume_model: ResumeModel, output_filename: str = "generated_resume") -> str:
        """Generate a minimal LaTeX resume with just the header."""
        doc = self._setup_document()
        
        # Add all sections
        self._add_all_sections(doc, resume_model)
        
        # Generate the PDF
        output_path = os.path.join(self.output_dir, output_filename)
        doc.generate_pdf(
            output_path,
            clean_tex=False,
            compiler='pdflatex',
            compiler_args=['-interaction=nonstopmode']
        )
        
        return output_path + '.pdf'

    def generate_latex(self, resume_model: ResumeModel) -> str:
        """Generate LaTeX content from a resume model without creating a PDF."""
        doc = self._setup_document()
        self._add_all_sections(doc, resume_model)
        return doc.dumps()

    def generate_pdf_from_latex(self, latex_content: str, output_filename: str = "generated_resume") -> str:
        """Generate a PDF file directly from LaTeX content string.
        
        Args:
            latex_content: The complete LaTeX document content as a string
            output_filename: The name of the output file (without extension)
            
        Returns:
            The path to the generated PDF file
        """
        doc = ResumeDocument()
        doc.dumps = lambda: latex_content  # Override dumps to return our content
        
        output_path = os.path.join(self.output_dir, output_filename)
        doc.generate_pdf(
            output_path,
            clean_tex=False,
            compiler='pdflatex',
            compiler_args=['-interaction=nonstopmode']
        )
        
        return output_path + '.pdf'

if __name__ == "__main__":
    from config import resume as default_resume
    generator = ResumeGenerator()
    
    # Test normal resume generation
    generator.generate_resume(default_resume)
    
    # Test latex generation and PDF from latex
    latex_content = generator.generate_latex(default_resume)
    generator.generate_pdf_from_latex(latex_content, "from_latex_test")
    print("Generated both PDFs - check the output directory") 