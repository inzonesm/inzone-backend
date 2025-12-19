#!/usr/bin/env python3
"""
InZone API Deployment Manager

Interactive script to manage local development and cloud deployments.
Automatically selects the correct environment files and deployment strategy.
"""

import os
import sys
import subprocess
from pathlib import Path

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text):
    """Print colored header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_success(text):
    """Print success message"""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text):
    """Print error message"""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_warning(text):
    """Print warning message"""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def print_info(text):
    """Print info message"""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def check_file_exists(filepath):
    """Check if a file exists"""
    return Path(filepath).exists()


def mask_sensitive_value(value, show_chars=6):
    """Mask sensitive values, showing only first few characters"""
    value = str(value).strip().strip("'\"")
    if len(value) <= show_chars:
        return "*" * len(value)
    return value[:show_chars] + "*" * (len(value) - show_chars)


def display_env_file(env_file, file_type="unknown"):
    """Display environment file contents with masked sensitive values"""
    print(f"\n{Colors.BOLD}{Colors.OKBLUE}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKBLUE}Environment File: {env_file} ({file_type}){Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKBLUE}{'='*60}{Colors.ENDC}\n")

    if not check_file_exists(env_file):
        print_error(f"{env_file} not found!")
        return

    try:
        with open(env_file, 'r') as f:
            lines = f.readlines()

        # Sensitive keys that should be masked
        sensitive_keys = [
            'API_KEY', 'SECRET', 'PASSWORD', 'TOKEN', 'CREDENTIALS',
            'PRIVATE', 'AUTH', 'KEY'
        ]

        print(f"{Colors.BOLD}Variable{' '*30}Value{Colors.ENDC}")
        print("-" * 60)

        for line in lines:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                if line.startswith('#'):
                    print(f"{Colors.WARNING}{line}{Colors.ENDC}")
                continue

            # Parse YAML format (KEY: 'value' or KEY: value)
            if ':' in line and not line.startswith('#'):
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip().strip("'\"")

                    # Check if this is a sensitive value
                    is_sensitive = any(sensitive_word in key.upper()
                                     for sensitive_word in sensitive_keys)

                    if is_sensitive and value:
                        display_value = mask_sensitive_value(value)
                        print(f"{Colors.OKCYAN}{key:35}{Colors.ENDC} {display_value}")
                    else:
                        print(f"{Colors.OKGREEN}{key:35}{Colors.ENDC} {value}")

            # Parse .env format (KEY=value or KEY="value")
            elif '=' in line and not line.startswith('#'):
                parts = line.split('=', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip().strip("'\"")

                    # Check if this is a sensitive value
                    is_sensitive = any(sensitive_word in key.upper()
                                     for sensitive_word in sensitive_keys)

                    if is_sensitive and value:
                        display_value = mask_sensitive_value(value)
                        print(f"{Colors.OKCYAN}{key:35}{Colors.ENDC} {display_value}")
                    else:
                        print(f"{Colors.OKGREEN}{key:35}{Colors.ENDC} {value}")

        print(f"\n{Colors.WARNING}Note: Sensitive values (API keys, secrets) are partially masked{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.OKBLUE}{'='*60}{Colors.ENDC}\n")

    except Exception as e:
        print_error(f"Error reading {env_file}: {str(e)}")


def validate_environment():
    """Validate that necessary files exist"""
    print_info("Validating environment files...")

    issues = []

    # Check for Docker
    if not check_file_exists("Dockerfile"):
        issues.append("Dockerfile not found")
    else:
        print_success("Dockerfile found")

    # Check for deployment scripts (now in scripts/)
    if not check_file_exists("scripts/deploy_cloud_run.sh"):
        issues.append("scripts/deploy_cloud_run.sh not found")
    else:
        print_success("Production deployment script found")

    if not check_file_exists("scripts/deploy_cloud_run_test.sh"):
        issues.append("scripts/deploy_cloud_run_test.sh not found")
    else:
        print_success("Test deployment script found")

    # Check for app.py
    if not check_file_exists("app.py"):
        issues.append("app.py not found")
    else:
        print_success("app.py found")

    # Check for required directories
    required_dirs = ["services", "routes", "config", "utils"]
    for dir_name in required_dirs:
        if not Path(dir_name).is_dir():
            issues.append(f"{dir_name}/ directory not found")
        else:
            print_success(f"{dir_name}/ directory found")

    return issues


def validate_env_file(env_file):
    """Validate environment file exists and has required variables"""
    if not check_file_exists(env_file):
        print_error(f"{env_file} not found!")
        return False

    # Read and check for required variables
    required_vars = ["OPENAI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"]
    missing_vars = []

    with open(env_file, 'r') as f:
        content = f.read()
        for var in required_vars:
            if var not in content:
                missing_vars.append(var)

    if missing_vars:
        print_warning(f"{env_file} is missing variables: {', '.join(missing_vars)}")
        return False

    print_success(f"{env_file} validated")
    return True


def run_local():
    """Run the application locally using .env file"""
    print_header("Running Locally")

    # Check for .env file
    if not check_file_exists(".env"):
        print_error(".env file not found!")
        print_info("Creating .env from .env.example...")

        if check_file_exists(".env.example"):
            subprocess.run(["cp", ".env.example", ".env"])
            print_warning("Please edit .env file with your actual API keys before running.")
            return
        else:
            print_error(".env.example not found! Cannot create .env file.")
            return

    print_success(".env file found")

    # Display environment file contents
    display_env_file(".env", "Local Development")

    # Check for key.json
    if not check_file_exists("key.json"):
        print_warning("key.json not found! You may need Firebase credentials.")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            return

    # Ask for port
    port = input(f"\nEnter port to run on (default: 5000): ").strip() or "5000"

    print_info(f"\nStarting Flask app on port {port}...")
    print_info("Press Ctrl+C to stop\n")

    try:
        # Set environment variable and run
        env = os.environ.copy()
        env["PORT"] = port
        subprocess.run(["python", "app.py"], env=env)
    except KeyboardInterrupt:
        print_info("\nShutting down...")


def deploy_to_test():
    """Deploy to test environment on Google Cloud Run"""
    print_header("Deploying to Test Environment")

    # Validate envs.test.yaml
    if not validate_env_file("envs.test.yaml"):
        print_error("Please fix envs.test.yaml before deploying")
        return

    # Display environment file contents
    display_env_file("envs.test.yaml", "Test Environment")

    # Check if gcloud is installed
    try:
        subprocess.run(["gcloud", "--version"], capture_output=True, check=True, shell=True)
        print_success("gcloud CLI found")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error("gcloud CLI not found! Please install Google Cloud SDK.")
        print_info("Visit: https://cloud.google.com/sdk/docs/install")
        return

    # Confirm deployment
    print_warning("\nYou are about to deploy to TEST environment:")
    print_info("  - Service: inzoneapi-test")
    print_info("  - Image: gcr.io/inzone-f93e4/inzoneapi:test")
    print_info("  - Region: us-central1")
    print_info("  - Environment: envs.test.yaml")

    response = input("\nProceed with deployment? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print_info("Deployment cancelled")
        return

    # Run deployment script
    print_info("\nStarting deployment...")
    try:
        if os.name == 'nt':  # Windows
            # Build image
            print_info("Building container image...")
            subprocess.run("gcloud builds submit --tag gcr.io/inzone-f93e4/inzoneapi:test", shell=True, check=True)
            # Deploy to Cloud Run
            print_info("Deploying to Cloud Run...")
            subprocess.run("gcloud run deploy inzoneapi-test --image gcr.io/inzone-f93e4/inzoneapi:test --region us-central1 --env-vars-file envs.test.yaml", shell=True, check=True)
        else:  # Unix/Linux/Mac
            subprocess.run(["bash", "scripts/deploy_cloud_run_test.sh"], check=True)
        print_success("\nTest deployment completed!")
        print_info("Check the URL above to access your test API")
    except subprocess.CalledProcessError:
        print_error("Deployment failed! Check the logs above for details.")


def deploy_to_production():
    """Deploy to production environment on Google Cloud Run"""
    print_header("Deploying to PRODUCTION Environment")

    # Validate envs.yaml
    if not validate_env_file("envs.yaml"):
        print_error("Please fix envs.yaml before deploying")
        return

    # Display environment file contents
    display_env_file("envs.yaml", "Production Environment")

    # Check if gcloud is installed
    try:
        subprocess.run(["gcloud", "--version"], capture_output=True, check=True, shell=True)
        print_success("gcloud CLI found")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error("gcloud CLI not found! Please install Google Cloud SDK.")
        print_info("Visit: https://cloud.google.com/sdk/docs/install")
        return

    # STRONG confirmation for production
    print_warning("\n" + "!"*60)
    print_warning("WARNING: You are about to deploy to PRODUCTION!")
    print_warning("!"*60)
    print_info("\n  - Service: inzoneapi")
    print_info("  - Image: gcr.io/inzone-f93e4/inzoneapi:latest")
    print_info("  - Region: us-central1")
    print_info("  - Environment: envs.yaml")
    print_warning("\nThis will affect live users!\n")

    response = input("Type 'deploy-production' to confirm: ")
    if response != 'deploy-production':
        print_info("Production deployment cancelled")
        return

    # Run deployment script
    print_info("\nStarting production deployment...")
    try:
        if os.name == 'nt':  # Windows
            # Build image
            print_info("Building container image...")
            subprocess.run("gcloud builds submit --tag gcr.io/inzone-f93e4/inzoneapi", shell=True, check=True)
            # Deploy to Cloud Run
            print_info("Deploying to Cloud Run...")
            subprocess.run("gcloud run deploy inzoneapi --image gcr.io/inzone-f93e4/inzoneapi --region us-central1 --env-vars-file envs.yaml", shell=True, check=True)
        else:  # Unix/Linux/Mac
            subprocess.run(["bash", "scripts/deploy_cloud_run.sh"], check=True)
        print_success("\nProduction deployment completed!")
        print_info("Your production API has been updated")
    except subprocess.CalledProcessError:
        print_error("Deployment failed! Check the logs above for details.")


def build_docker_only():
    """Build Docker image without deploying"""
    print_header("Building Docker Image")

    tag = input("Enter image tag (default: local-test): ").strip() or "local-test"

    print_info(f"\nBuilding Docker image with tag: {tag}...")
    try:
        subprocess.run([
            "docker", "build",
            "-t", f"inzoneapi:{tag}",
            "."
        ], check=True)
        print_success(f"\nDocker image built successfully: inzoneapi:{tag}")
        print_info(f"Run locally with: docker run -p 8080:8080 --env-file .env inzoneapi:{tag}")
    except subprocess.CalledProcessError:
        print_error("Docker build failed!")


def show_environment_status():
    """Show status of all environment files"""
    print_header("Environment Files Status")

    print(f"{Colors.BOLD}Template Files (safe to commit):{Colors.ENDC}\n")
    template_files = {
        ".env.example": "Python dotenv template",
        "envs.example.yaml": "YAML template - all required vars",
        "envs.local.yaml": "Local development template",
        "envs.test.yaml": "Test environment template"
    }
    for file, description in template_files.items():
        status = "✓ EXISTS" if check_file_exists(file) else "✗ MISSING"
        color = Colors.OKGREEN if check_file_exists(file) else Colors.WARNING
        print(f"{color}{status}{Colors.ENDC} - {file:25} ({description})")

    print(f"\n{Colors.BOLD}Secret Files (gitignored, DO NOT commit):{Colors.ENDC}\n")
    secret_files = {
        ".env": "Local Python dotenv secrets",
        "envs.yaml": "Production secrets",
        "envs.dev.yaml": "Development secrets",
        "envs.staging.yaml": "Staging secrets",
        "key.json": "Firebase service account key"
    }
    for file, description in secret_files.items():
        status = "✓ EXISTS" if check_file_exists(file) else "✗ MISSING"
        color = Colors.OKGREEN if check_file_exists(file) else Colors.FAIL
        print(f"{color}{status}{Colors.ENDC} - {file:25} ({description})")

    # Ask if user wants to see contents
    print(f"\n{Colors.BOLD}Would you like to see the contents of the environment files?{Colors.ENDC}")
    print("1. View .env (Local Python)")
    print("2. View envs.local.yaml (Local YAML template)")
    print("3. View envs.test.yaml (Test)")
    print("4. View envs.yaml (Production)")
    print("5. View all")
    print("6. Back to main menu")

    choice = input(f"\n{Colors.BOLD}Enter your choice (1-6): {Colors.ENDC}").strip()

    if choice == "1" and check_file_exists(".env"):
        display_env_file(".env", "Local Development")
    elif choice == "2" and check_file_exists("envs.local.yaml"):
        display_env_file("envs.local.yaml", "Local Development Template")
    elif choice == "3" and check_file_exists("envs.test.yaml"):
        display_env_file("envs.test.yaml", "Test Environment")
    elif choice == "4" and check_file_exists("envs.yaml"):
        display_env_file("envs.yaml", "Production Environment")
    elif choice == "5":
        if check_file_exists(".env"):
            display_env_file(".env", "Local Development")
        if check_file_exists("envs.local.yaml"):
            display_env_file("envs.local.yaml", "Local Development Template")
        if check_file_exists("envs.test.yaml"):
            display_env_file("envs.test.yaml", "Test Environment")
        if check_file_exists("envs.yaml"):
            display_env_file("envs.yaml", "Production Environment")
    elif choice == "6":
        return
    else:
        print_error("Invalid choice or file does not exist")


def show_project_structure():
    """Show the current project structure"""
    print_header("Project Structure")

    print(f"{Colors.BOLD}InZone API Directory Structure:{Colors.ENDC}\n")

    structure = {
        "Root Files": ["app.py", "config.py", "dependencies.py", "Dockerfile", ".gitignore"],
        "Configuration": ["config/", "envs.example.yaml", "envs.local.yaml", "envs.test.yaml"],
        "Core Modules": ["services/", "routes/", "models/", "utils/"],
        "Deployment": ["scripts/", "docs/"],
        "Testing & Static": ["tests/", "static/"],
        "Documentation": ["docs/", "ENV_SETUP.md", "README.md"]
    }

    for category, items in structure.items():
        print(f"\n{Colors.BOLD}{Colors.OKCYAN}{category}:{Colors.ENDC}")
        for item in items:
            if item.endswith('/'):
                # Directory
                is_dir = Path(item).is_dir()
                status = "✓" if is_dir else "✗"
                color = Colors.OKGREEN if is_dir else Colors.FAIL
                print(f"  {color}{status}{Colors.ENDC} {item}")
            else:
                # File
                exists = check_file_exists(item)
                status = "✓" if exists else "✗"
                color = Colors.OKGREEN if exists else Colors.WARNING
                print(f"  {color}{status}{Colors.ENDC} {item}")

    print(f"\n{Colors.BOLD}Key Directories:{Colors.ENDC}")
    key_dirs = {
        "services/": "Business logic and service layer",
        "routes/": "API endpoints and route handlers",
        "config/": "Configuration files",
        "utils/": "Utility functions and helpers",
        "scripts/": "Deployment and maintenance scripts",
        "docs/": "Documentation files",
        "tests/": "Test files and scripts",
        "static/": "Static files (HTML, CSS, JS)"
    }

    for dir_name, description in key_dirs.items():
        exists = Path(dir_name).is_dir()
        status = "✓" if exists else "✗"
        color = Colors.OKGREEN if exists else Colors.FAIL
        print(f"  {color}{status} {dir_name:15}{Colors.ENDC} - {description}")

    print(f"\n{Colors.OKCYAN}Tip: Run 'tree -L 2' in terminal to see detailed structure{Colors.ENDC}")


def main():
    """Main function"""
    print_header("InZone API Deployment Manager")

    # Change to project root directory (parent of scripts/)
    script_dir = Path(__file__).parent  # This is scripts/
    project_root = script_dir.parent    # This is inzoneapi/
    os.chdir(project_root)

    print_info(f"Working directory: {os.getcwd()}")

    # Validate environment
    issues = validate_environment()
    if issues:
        print_error("Environment validation failed:")
        for issue in issues:
            print(f"  - {issue}")
        print_info("\nPlease fix these issues before proceeding.")
        sys.exit(1)

    print_success("Environment validation passed!\n")

    # Main menu
    while True:
        print(f"\n{Colors.BOLD}What would you like to do?{Colors.ENDC}\n")
        print("1. Run locally (uses .env)")
        print("2. Deploy to TEST environment (uses envs.test.yaml)")
        print("3. Deploy to PRODUCTION environment (uses envs.yaml)")
        print("4. Build Docker image only (no deployment)")
        print("5. Show environment files status")
        print("6. View project structure")
        print("7. Exit")

        choice = input(f"\n{Colors.BOLD}Enter your choice (1-7): {Colors.ENDC}").strip()

        if choice == "1":
            run_local()
        elif choice == "2":
            deploy_to_test()
        elif choice == "3":
            deploy_to_production()
        elif choice == "4":
            build_docker_only()
        elif choice == "5":
            show_environment_status()
        elif choice == "6":
            show_project_structure()
        elif choice == "7":
            print_info("Goodbye!")
            break
        else:
            print_error("Invalid choice! Please enter 1-7")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_info("\n\nExiting...")
        sys.exit(0)
