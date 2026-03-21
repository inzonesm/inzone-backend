#!/usr/bin/env python3
import csv
import os
import sys
import firebase_admin
from firebase_admin import credentials, firestore
import argparse
import uuid

def initialize_firebase():
    """
    Initialize Firebase connection
    
    Returns:
        Firestore client instance
    """
    try:
        # If already initialized, use the existing app
        db = firestore.client()
        print("Using existing Firebase connection")
    except ValueError:
        # Otherwise initialize Firebase
        credential_path = "/Users/aryan/Inzone/agent_dashboard/key.json"
        
        if not os.path.exists(credential_path):
            print(f"Error: Firebase credential file not found at {credential_path}")
            sys.exit(1)
            
        cred = credentials.Certificate(credential_path)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Firebase initialized successfully")
        
    return db

def read_csv_file(file_path):
    """
    Read character data from a CSV file
    
    Args:
        file_path (str): Path to the CSV file
        
    Returns:
        list: List of dictionaries containing character data
    """
    if not os.path.exists(file_path):
        print(f"Error: CSV file not found at {file_path}")
        sys.exit(1)
    
    characters = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as csv_file:
            # First, try with comma delimiter (standard CSV)
            csv_reader = csv.DictReader(csv_file)
            
            # Check if required columns exist
            required_cols = ['Name', 'Description', 'Greeting']
            if not all(col in csv_reader.fieldnames for col in required_cols):
                # Reset file pointer to beginning
                csv_file.seek(0)
                
                # Try with tab delimiter as fallback
                csv_reader = csv.DictReader(csv_file, delimiter='\t')
                
                # Check again with tab delimiter
                if not all(col in csv_reader.fieldnames for col in required_cols):
                    missing = [col for col in required_cols if col not in csv_reader.fieldnames]
                    print(f"Error: CSV is missing required columns: {missing}")
                    print(f"Available columns: {csv_reader.fieldnames}")
                    sys.exit(1)
                    
            # Reset file pointer to skip header row
            csv_file.seek(0)
            next(csv_file)  # Skip header
            
            # Re-create reader with the correct delimiter
            delimiter = ',' if ',' in next(csv_file).split('\n')[0] else '\t'
            csv_file.seek(0)
            next(csv_file)  # Skip header again
            csv_reader = csv.DictReader(csv_file, fieldnames=["Group #", "Common Denominator", "Name", "Description", "Greeting"], delimiter=delimiter)
                
            # Process each row
            for row in csv_reader:
                # Make sure we have all required data
                if not all(key in row and row[key] for key in ['Name', 'Description', 'Greeting']):
                    continue
                    
                character = {
                    'name': row['Name'].strip(),
                    'personality': row['Description'].strip(),
                    'greeting': row['Greeting'].strip(),
                    'numberOfChats': 0,
                    'profile_picture_url': "",
                    'votes': ""
                }
                characters.append(character)
                
        print(f"Read {len(characters)} characters from CSV file")
        return characters
    except Exception as e:
        print(f"Error reading CSV file: {str(e)}")
        sys.exit(1)

def character_exists(db, name):
    """
    Check if a character with the given name already exists in the collection
    
    Args:
        db: Firestore client instance
        name (str): Name of the character to check
        
    Returns:
        bool: True if exists, False otherwise
    """
    characters_ref = db.collection("popularCharacters")
    query = characters_ref.where("name", "==", name).limit(1)
    results = query.get()
    
    return len(results) > 0

def add_characters_to_firestore(db, characters, check_duplicates=True):
    """
    Add characters to Firestore popularCharacters collection
    
    Args:
        db: Firestore client instance
        characters (list): List of character dictionaries
        check_duplicates (bool): Whether to check for and skip duplicates
        
    Returns:
        tuple: (added_count, skipped_count)
    """
    characters_ref = db.collection("popularCharacters")
    added_count = 0
    skipped_count = 0
    
    for character in characters:
        name = character['name']
        
        # Skip duplicates if requested
        if check_duplicates and character_exists(db, name):
            print(f"Skipping duplicate character: {name}")
            skipped_count += 1
            continue
            
        # Generate a document ID (using uuid4 for uniqueness)
        doc_id = str(uuid.uuid4())
        
        # Add character to Firestore
        characters_ref.document(doc_id).set(character)
        added_count += 1
        print(f"Added character: {name} (ID: {doc_id})")
        
    return added_count, skipped_count

def main():
    parser = argparse.ArgumentParser(description="Import characters from CSV to Firebase Firestore")
    parser.add_argument("csv_file", help="Path to the CSV file containing character data")
    parser.add_argument("--force", action="store_true", help="Skip checking for duplicates")
    
    args = parser.parse_args()
    
    # Initialize Firebase
    print("Initializing Firebase...")
    db = initialize_firebase()
    
    # Read characters from CSV
    print(f"Reading characters from {args.csv_file}...")
    characters = read_csv_file(args.csv_file)
    
    if not characters:
        print("No valid characters found in the CSV file.")
        return
    
    # Add characters to Firestore
    print("Adding characters to Firestore...")
    added, skipped = add_characters_to_firestore(
        db, 
        characters, 
        check_duplicates=(not args.force)
    )
    
    print(f"\nSummary:")
    print(f"- Characters added: {added}")
    print(f"- Characters skipped (duplicates): {skipped}")
    print(f"- Total characters processed: {added + skipped}")
    print("Done!")

if __name__ == "__main__":
    main()
