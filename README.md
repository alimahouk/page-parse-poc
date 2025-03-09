# Page Parsing Proof-of-Concept

A PoC project for advanced web page parsing and analysis using AI and computer vision techniques. This project combines web scraping, document intelligence, and image analysis to extract and process information from web pages.

This parser only parses the currently visible part of the page in the viewport rather than the entire page and constructs a DOM-like JSON structure out of it for passing to an LLM without taking up the entire context window.

## Features

- Web page scraping using Selenium
- Document analysis with Azure AI Document Intelligence
- Image analysis with Azure Computer Vision
- Text processing with OpenAI and sentence transformers
- Computer vision operations with OpenCV
- Hovering over visible elements to detect hidden elements that may appear as a result

## Prerequisites

- Python 3.11
- Poetry for dependency management
- Azure account with Document Intelligence and Computer Vision services
- OpenAI API key
- Chrome/Chromium browser (for Selenium)

## Installation

1. Clone the repository:

    ```bash
    git clone https://github.com/yourusername/page-parse-poc.git
    cd page-parse-poc
    ```

2. Install dependencies using Poetry:

    ```bash
    poetry install
    ```

3. Set up environment variables:
    Create a `.env` file in the project root with the following variables:

    ```
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=your_endpoint
    AZURE_DOCUMENT_INTELLIGENCE_KEY=your_key
    AZURE_VISION_ENDPOINT=your_endpoint
    AZURE_VISION_KEY=your_key
    OPENAI_API_KEY=your_key
    ```

## Project Structure

- `ui/` - Output images for vision analysis
- `web_browser/` - Web browsing and scraping functionality
- `pyproject.toml` - Project dependencies and configuration

## Development

This project uses Poetry for dependency management. To add new dependencies:

```bash
poetry add package-name
```

To activate the virtual environment:

```bash
poetry shell
```

## License

This project is licensed under the terms included in the LICENSE file.

## Author

Created by Ali Mahouk in 2024-2025.
