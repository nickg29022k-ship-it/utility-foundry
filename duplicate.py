import csv
from collections import defaultdict
from fuzzywuzzy import fuzz

def load_data(filename):
    roles = []
    with open(filename, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            roles.append(row)
    return roles

def find_duplicates(roles):
    duplicates = []
    
    for i, role1 in enumerate(roles):
        for j, role2 in enumerate(roles[i+1:], i+1):
            # Calculate similarity scores for each attribute
            desc_score = fuzz.ratio(role1['Role Description'].lower(), role2['Role Description'].lower())
            app_score = fuzz.ratio(role1['Application Name'].lower(), role2['Application Name'].lower())
            ent_score = fuzz.ratio(role1['Entitlement Value'].lower(), role2['Entitlement Value'].lower())
            
            # Calculate overall similarity percentage
            avg_score = (desc_score + app_score + ent_score) / 3
            
            if avg_score >= 80:  # 80% similarity threshold
                duplicates.append({
                    'role1': role1,
                    'role2': role2,
                    'scores': {
                        'description': desc_score,
                        'application': app_score,
                        'entitlement': ent_score,
                        'overall': avg_score
                    }
                })
    
    return duplicates

def generate_report(duplicates, output_file):
    with open(output_file, 'w') as f:
        f.write("DUPLICATE ROLES REPORT\n")
        f.write("=" * 50 + "\n\n")
        
        for i, dup in enumerate(duplicates, 1):
            r1, r2 = dup['role1'], dup['role2']
            scores = dup['scores']
            
            f.write(f"DUPLICATE GROUP {i} ({scores['overall']:.1f}% match)\n")
            f.write(f"Role 1: {r1['Role Name']} (ID: {r1['Role ID']})\n")
            f.write(f"Role 2: {r2['Role Name']} (ID: {r2['Role ID']})\n")
            f.write(f"Description Similarity: {scores['description']}%\n")
            f.write(f"Application Similarity: {scores['application']}%\n")
            f.write(f"Entitlement Similarity: {scores['entitlement']}%\n")
            f.write("-" * 40 + "\n\n")

if __name__ == '__main__':
    roles = load_data('Entitlements_roles_Raw.csv')
    duplicates = find_duplicates(roles)
    generate_report(duplicates, 'duplicate_roles_report.txt')
    
    print(f"Found {len(duplicates)} potential duplicate pairs")
    print("Report saved to 'duplicate_roles_report.txt'")