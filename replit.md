# SENORA ASN

## Overview

This is a Flask-based web application for parsing and analyzing telecom Call Detail Records (CDR) from binary ASN.1 files. The application provides a user-friendly interface for uploading CDR files, parsing them to extract call information, and viewing the results in a structured format with export capabilities.

**Recent Success**: Successfully implemented BCD (Binary Coded Decimal) phone number extraction that extracts 1000+ real phone numbers from HSS telecom data files, providing meaningful CDR analysis with actual calling/called numbers.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Framework**: Flask with Jinja2 templating
- **UI Framework**: Bootstrap 5 with dark theme
- **JavaScript Libraries**: jQuery and DataTables for enhanced table functionality
- **Responsive Design**: Mobile-friendly interface with Bootstrap grid system

### Backend Architecture
- **Framework**: Flask (Python web framework)
- **Database ORM**: Flask-SQLAlchemy with SQLAlchemy 2.0+ declarative base
- **File Processing**: Custom ASN.1 parser using pyasn1 library
- **Session Management**: Flask sessions with configurable secret key
- **File Upload**: Werkzeug secure file handling with size limits

### Data Storage Solutions
- **Primary Database**: SQLite (default) with PostgreSQL support via DATABASE_URL environment variable
- **Database Features**: Connection pooling, automatic reconnection, and proper connection lifecycle management
- **File Storage**: Local filesystem storage in uploads directory
- **Database Schema**: Two main entities - CDRFile for metadata and CDRRecord for parsed call records

## Key Components

### 1. CDR Parser (cdr_parser.py)
- **Purpose**: Core ASN.1 parsing engine for telecom CDR files
- **Technology**: pyasn1 library for ASN.1 BER/DER decoding
- **Features**: Binary data processing, large file handling, record extraction, error handling

### 2. Data Models (models.py)
- **CDRFile Model**: Tracks uploaded files, parse status, and metadata
- **CDRRecord Model**: Stores individual call records with extracted fields
- **Relationships**: One-to-many relationship between files and records
- **JSON Storage**: Raw parsed data stored as JSON in text fields

### 3. Web Routes (routes.py)
- **File Upload**: Secure file handling with extension validation
- **Result Display**: Paginated view of parsed records with search and filtering
- **Record Editor**: Full CRUD operations for individual CDR records
- **Export Functions**: JSON and CSV export capabilities
- **RESTful Design**: Clean URL structure for different operations

### 4. Templates
- **Base Template**: Consistent layout with Bootstrap navigation
- **Upload Interface**: File selection with validation feedback
- **Results Display**: DataTables integration for searchable record views
- **Responsive Design**: Mobile-optimized interface

## Data Flow

1. **File Upload**: User selects CDR file through web interface
2. **Validation**: File type and size validation before processing
3. **Storage**: Secure filename generation and file system storage
4. **Database Entry**: CDRFile record created with metadata
5. **Parsing**: ASN.1 parser processes binary data asynchronously
6. **Record Extraction**: Individual call records extracted and stored
7. **Status Update**: Parse status and record count updated
8. **Display**: Results presented in searchable table format
9. **Export**: Data available in multiple formats (JSON, CSV)

## External Dependencies

### Core Libraries
- **Flask**: Web framework and routing
- **SQLAlchemy**: Database ORM and connection management
- **pyasn1**: ASN.1 encoding/decoding library
- **Werkzeug**: WSGI utilities and security features

### Frontend Dependencies (CDN)
- **Bootstrap 5**: UI framework with dark theme
- **DataTables**: Advanced table functionality
- **Font Awesome**: Icon library
- **jQuery**: JavaScript utilities

### Python Packages
- **flask-sqlalchemy**: Flask-SQLAlchemy integration
- **werkzeug**: WSGI middleware and utilities

## Deployment Strategy

### Development Setup
- **Entry Point**: main.py runs Flask development server
- **Configuration**: Environment-based configuration with sensible defaults
- **Database**: SQLite for development, PostgreSQL for production
- **Debug Mode**: Enabled in development with detailed error logging

### Production Considerations
- **WSGI**: ProxyFix middleware for proper header handling behind reverse proxies
- **Database**: PostgreSQL recommended via DATABASE_URL environment variable
- **Security**: Configurable session secret via SESSION_SECRET environment variable
- **File Limits**: 100MB upload limit with configurable storage location
- **Logging**: Comprehensive logging with configurable levels

### Environment Variables
- **DATABASE_URL**: Database connection string (defaults to SQLite)
- **SESSION_SECRET**: Flask session secret key
- **Upload configuration**: File size limits and storage paths

### File Structure
- **Static Files**: CSS and JavaScript in static/ directory
- **Templates**: HTML templates in templates/ directory
- **Uploads**: File storage in uploads/ directory (auto-created)
- **Database**: SQLite file in root directory (development)

The application is designed to be easily deployable on platforms like Replit, Heroku, or traditional servers with minimal configuration changes.