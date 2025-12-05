import json
import sys
from collections import defaultdict

def extract_retool_info(file_path):
    """Extract pages, components, queries, and workflows from Retool JSON"""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    app_data = data.get('page', {}).get('data', {})
    pages = app_data.get('pages', [])
    queries = app_data.get('queries', [])
    
    info = {
        'pages': [],
        'components_by_page': defaultdict(list),
        'queries': [],
        'workflows': []
    }
    
    # Extract pages
    for page in pages:
        page_info = {
            'name': page.get('name', 'Unnamed'),
            'id': page.get('id'),
            'components': []
        }
        
        # Extract components from page
        components = page.get('components', [])
        for comp in components:
            comp_info = {
                'type': comp.get('component', {}).get('type', 'unknown'),
                'name': comp.get('component', {}).get('name', 'Unnamed'),
                'label': comp.get('component', {}).get('label', ''),
                'text': comp.get('component', {}).get('text', ''),
                'query': comp.get('component', {}).get('query', {}).get('name', '') if comp.get('component', {}).get('query') else '',
                'tableColumns': comp.get('component', {}).get('tableColumns', []),
                'actions': comp.get('component', {}).get('actions', []),
            }
            page_info['components'].append(comp_info)
            info['components_by_page'][page_info['name']].append(comp_info)
        
        info['pages'].append(page_info)
    
    # Extract queries
    for query in queries:
        query_info = {
            'name': query.get('name', 'Unnamed'),
            'type': query.get('type', 'unknown'),
            'resource': query.get('resource', {}).get('name', '') if query.get('resource') else '',
            'query': query.get('query', ''),
        }
        info['queries'].append(query_info)
    
    return info

if __name__ == '__main__':
    file_path = 'Nord App - Production (1).json'
    info = extract_retool_info(file_path)
    
    print("=" * 80)
    print("RETOOL APPLICATION ANALYSIS")
    print("=" * 80)
    print(f"\nTotal Pages: {len(info['pages'])}")
    print(f"Total Queries: {len(info['queries'])}")
    
    print("\n" + "=" * 80)
    print("PAGES:")
    print("=" * 80)
    for page in info['pages']:
        print(f"\n📄 {page['name']}")
        print(f"   Components: {len(page['components'])}")
        component_types = defaultdict(int)
        for comp in page['components']:
            component_types[comp['type']] += 1
        for comp_type, count in component_types.items():
            print(f"   - {comp_type}: {count}")
    
    print("\n" + "=" * 80)
    print("QUERIES:")
    print("=" * 80)
    query_types = defaultdict(int)
    for query in info['queries']:
        query_types[query['type']] += 1
    for qtype, count in query_types.items():
        print(f"   - {qtype}: {count}")

