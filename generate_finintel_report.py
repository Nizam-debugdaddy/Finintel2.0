from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

OUTPUT_PATH = r"d:\Desktop\finintel\FinIntel_Internship_Report.docx"


def set_margins(section):
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1.2)
    section.right_margin = Inches(1.2)


def add_page_break(doc):
    doc.add_page_break()


def add_centered_paragraph(doc, text, size=16, bold=False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    return p


def add_heading(doc, text, level=1):
    doc.add_heading(text, level=level)


def add_paragraph(doc, text, size=11, bold=False, italic=False):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    return p


def add_bullets(doc, items):
    for item in items:
        doc.add_paragraph(item, style='List Bullet')


def add_section_break(doc):
    doc.add_page_break()


def main():
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(11)

    # Title page
    add_centered_paragraph(doc, 'FININTEL', 24, True)
    add_centered_paragraph(doc, 'Web-Based Financial Analytics and Reporting Platform', 18, True)
    add_centered_paragraph(doc, 'Internship Report', 16, True)
    doc.add_paragraph()
    add_centered_paragraph(doc, 'Submitted by', 12, True)
    add_centered_paragraph(doc, '[Your Name]', 14, True)
    add_centered_paragraph(doc, '[Your Roll Number / Student ID]', 12, False)
    doc.add_paragraph()
    add_centered_paragraph(doc, 'Department of [Your Department]', 12, False)
    add_centered_paragraph(doc, '[Your College / University Name]', 12, False)
    doc.add_paragraph()
    add_centered_paragraph(doc, 'Under the guidance of', 12, True)
    add_centered_paragraph(doc, '[Mentor / Supervisor Name]', 13, True)
    add_centered_paragraph(doc, '[Organization / Company Name]', 12, False)
    doc.add_paragraph()
    add_centered_paragraph(doc, 'Month Year', 12, False)

    add_page_break(doc)

    # Certificate
    add_heading(doc, 'Certificate', 1)
    add_paragraph(doc, 'This is to certify that [Your Name], student of [Your College / University Name], has successfully completed the internship project titled “FinIntel: Web-Based Financial Analytics and Reporting Platform” under my supervision.')
    add_paragraph(doc, 'The work completed is original and has been carried out with sincerity and diligence during the internship period.')
    doc.add_paragraph()
    add_paragraph(doc, '__________________________')
    add_paragraph(doc, '[Supervisor Name]')
    add_paragraph(doc, '[Designation]')
    add_paragraph(doc, '[Organization Name]')

    add_page_break(doc)

    # Declaration
    add_heading(doc, 'Declaration', 1)
    add_paragraph(doc, 'I, [Your Name], hereby declare that the internship report entitled “FinIntel: Web-Based Financial Analytics and Reporting Platform” is my own work and has not been submitted earlier for any degree, diploma, or similar title.')
    add_paragraph(doc, 'I further declare that all information included in this report is based on my own study and the work carried out during the internship period.')
    doc.add_paragraph()
    add_paragraph(doc, '__________________________')
    add_paragraph(doc, '[Your Name]')
    add_paragraph(doc, '[Roll Number / Student ID]')

    add_page_break(doc)

    # Acknowledgement
    add_heading(doc, 'Acknowledgement', 1)
    add_paragraph(doc, 'I would like to express my sincere gratitude to my internship supervisor, faculty members, and colleagues for their constant guidance, encouragement, and support throughout this project. Their valuable suggestions helped me understand the practical application of software development and financial analysis in a real-world environment.')
    add_paragraph(doc, 'I also thank the organization for providing me with the opportunity to work on this project and gain valuable hands-on experience in web application development, analytics integration, and reporting workflows.')

    add_page_break(doc)

    # Abstract
    add_heading(doc, 'Abstract', 1)
    add_paragraph(doc, 'FinIntel is a web-based financial analytics and reporting platform designed to modernize traditional financial analysis workflows. The project addresses the limitations of manual spreadsheet-based methods by providing an integrated environment for financial data entry, analysis, dashboarding, peer comparison, and export-ready reporting. The platform combines a React-based frontend, a FastAPI backend, a SQLite metadata layer, and warehouse-backed analysis services to deliver a scalable and practical solution for financial evaluation. The system supports cost structure analysis and bankruptcy risk assessment using the Altman Z-score methodology. Overall, the project demonstrates how established financial concepts can be effectively integrated into a modern digital platform to improve efficiency, consistency, and decision-making.')

    add_page_break(doc)

    # Chapter 1
    add_heading(doc, 'Chapter 1', 1)
    add_heading(doc, 'Introduction', 2)
    add_paragraph(doc, 'In today’s competitive business environment, financial analysis plays a critical role in strategic planning, performance evaluation, and decision-making. Companies continuously assess profitability, liquidity, solvency, and risk exposure to remain competitive and sustainable. Traditionally, such analysis has been carried out using manual spreadsheets and disconnected tools, which are often time-consuming and prone to inconsistency.')
    add_paragraph(doc, 'The project FinIntel was developed to address these limitations by providing a web-based platform for financial input, analytics, comparison, and reporting. The system aims to reduce manual effort, improve accuracy, and present financial insights in a more structured and accessible format.')
    add_paragraph(doc, 'The main objectives of this project are to enable efficient financial data entry, automate analysis, provide dashboards and peer comparison, and generate export-ready reports in Excel, PowerPoint, and PDF formats. The project is significant because it modernizes the financial analysis workflow and brings together several related functions into a single digital environment.')

    add_page_break(doc)

    # Chapter 2
    add_heading(doc, 'Chapter 2', 1)
    add_heading(doc, 'Literature Review and Theoretical Background', 2)
    add_paragraph(doc, 'Financial analysis is an essential part of corporate decision-making. It helps organizations understand their operational performance, identify weaknesses, and make informed strategic decisions. The analysis of profit and loss statements, balance sheets, and key financial ratios provides critical insight into profitability, leverage, efficiency, and solvency.')
    add_paragraph(doc, 'Cost structure analysis is widely used to understand how a company allocates its operating expenses across major categories such as raw materials, manpower, power, transportation, and depreciation. This analysis helps management identify inefficiencies and improve cost discipline.')
    add_paragraph(doc, 'Financial distress is another important area of analysis. One of the most recognized methods for assessing bankruptcy risk is the Altman Z-score model. The model combines five financial ratios to produce a single score that reflects the likelihood of financial distress. The formula is given as:')
    add_paragraph(doc, 'Z = 1.2X1 + 1.4X2 + 3.3X3 + 0.6X4 + 1.0X5')
    add_paragraph(doc, 'The Altman Z-score was chosen for this project because it is a widely accepted, standardized, and interpretable measure of bankruptcy risk. It incorporates liquidity, profitability, leverage, solvency, and operational performance into one score, making it easier for analysts to evaluate company health quickly and consistently.')

    add_page_break(doc)

    # Chapter 3
    add_heading(doc, 'Chapter 3', 1)
    add_heading(doc, 'Methodology', 2)
    add_paragraph(doc, 'The methodology used in this project followed a modular and practical approach. The system was designed in components covering company management, financial input, analysis, dashboarding, peer comparison, and reporting. This modular approach made the platform easier to implement, test, and extend.')
    add_paragraph(doc, 'The data workflow begins with financial information entered by the user through the web interface. The data is stored in a staging layer, processed through backend services, and used by the analytics engines to generate results. This structured workflow separates raw input from final analytical output and supports a more reliable analysis process.')
    add_paragraph(doc, 'The project also reused existing legacy analysis engines instead of rebuilding the entire financial logic from scratch. This not only preserved proven analytical functionality but also allowed the system to be modernized through a web-based interface. The methodology therefore combines software engineering practices with domain-specific financial analysis techniques.')

    add_page_break(doc)

    # Chapter 4
    add_heading(doc, 'Chapter 4', 1)
    add_heading(doc, 'System Architecture and Implementation', 2)
    add_paragraph(doc, 'The architecture of the FinIntel platform is organized into several layers. The frontend provides the user interface for navigation, data entry, dashboards, peer analysis, and export actions. The backend handles API requests, system logic, and orchestration between the database and the analytics engines.')
    add_paragraph(doc, 'The data layer uses SQLite for metadata and staging information, while the warehouse-based storage model is used for financial records and analysis data. This layered architecture enhances maintainability, scalability, and future extension of the system.')
    add_paragraph(doc, 'The analytics layer integrates legacy financial engines for cost structure analysis and bankruptcy assessment. These engines are invoked through a service layer, which prepares and standardizes the data before presentation. The reporting module further converts analysis results into Excel, PowerPoint, and PDF documents for end-user consumption.')

    add_page_break(doc)

    # Chapter 5
    add_heading(doc, 'Chapter 5', 1)
    add_heading(doc, 'Features and Functionality', 2)
    add_paragraph(doc, 'The FinIntel platform provides a wide range of useful features for financial analysis. It supports company and sector management, financial input templates, and multi-period data handling. The input interface allows analysts to enter financial values in a structured and organized way.')
    add_paragraph(doc, 'The platform also includes dashboard-based KPI visualization, peer comparison, cost structure analysis, and bankruptcy-risk assessment. These features allow users to understand financial performance quickly and compare companies in a meaningful way. The export module adds further value by enabling users to generate export-ready reports for documentation and presentation.')

    add_page_break(doc)

    # Chapter 6
    add_heading(doc, 'Chapter 6', 1)
    add_heading(doc, 'Results and Discussion', 2)
    add_paragraph(doc, 'The completed project successfully demonstrates how a traditional financial analysis workflow can be transformed into a modern web-based system. The implementation provides a practical environment for entering financial data, running analysis, reviewing results, and generating reports from a single platform.')
    add_paragraph(doc, 'The system improves efficiency by reducing manual effort and increasing consistency in reporting. It also supports better data traceability and makes financial insights more accessible to users. The integration of dashboards, peer comparison, and reporting tools adds significant practical value to the platform.')
    add_paragraph(doc, 'Although the project is functional and comprehensive, there is still scope for further enhancement. Future improvements may include broader multi-user support, improved collaboration features, integration with external financial data sources, and advanced forecasting capabilities.')

    add_page_break(doc)

    # Chapter 7
    add_heading(doc, 'Chapter 7', 1)
    add_heading(doc, 'Conclusion and Future Scope', 2)
    add_paragraph(doc, 'In conclusion, FinIntel is a successful internship project that combines financial analysis with modern web application development. The platform offers a practical and integrated solution for financial input, analysis, dashboarding, peer benchmarking, and reporting. It demonstrates the relevance of digital transformation in the field of financial analytics.')
    add_paragraph(doc, 'The project has strong future potential. With further enhancement, the system can evolve into a more powerful enterprise-level platform capable of supporting larger datasets, collaborative workflows, and advanced analytical features. The project therefore provides a strong foundation for continued development and real-world deployment.')

    add_page_break(doc)

    # References
    add_heading(doc, 'References', 1)
    add_paragraph(doc, 'Altman, E. I. (1968). Financial Ratios, Discriminant Analysis and the Prediction of Corporate Bankruptcy. Journal of Finance.')
    add_paragraph(doc, 'Damodaran, A. (2012). Investment Valuation. Wiley.')
    add_paragraph(doc, 'FastAPI Documentation. https://fastapi.tiangolo.com')
    add_paragraph(doc, 'React Documentation. https://react.dev')
    add_paragraph(doc, 'Python Documentation. https://docs.python.org')

    add_page_break(doc)

    # Appendix
    add_heading(doc, 'Appendix', 1)
    add_paragraph(doc, 'Appendix A: Summary of Major Modules')
    add_bullets(doc, [
        'Company and sector management module',
        'Financial input and staged data workflow',
        'Analytics engine orchestration service',
        'Dashboard and peer comparison module',
        'Export generation for Excel, PPT, and PDF'
    ])
    add_paragraph(doc, 'Appendix B: Key Technologies Used')
    add_bullets(doc, [
        'Python and FastAPI',
        'React and TypeScript',
        'SQLite and warehouse-based financial storage',
        'Pandas, DuckDB, and reporting libraries'
    ])

    # Set section page size and margins
    for section in doc.sections:
        set_margins(section)

    doc.save(OUTPUT_PATH)
    print(f'Report created: {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
