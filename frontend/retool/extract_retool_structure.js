// Node.js script to extract basic structure from Retool JSON
// Run with: node extract_retool_structure.js

const fs = require('fs');
const path = require('path');

function extractRetoolStructure() {
  try {
    const filePath = path.join(__dirname, 'Nord App - Production (1).json');
    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    
    const appData = data?.page?.data || {};
    const pages = appData.pages || [];
    const queries = appData.queries || [];
    
    console.log('='.repeat(80));
    console.log('RETOOL APPLICATION STRUCTURE');
    console.log('='.repeat(80));
    
    console.log(`\nTotal Pages: ${pages.length}`);
    console.log(`Total Queries: ${queries.length}\n`);
    
    // Extract page information
    console.log('='.repeat(80));
    console.log('PAGES:');
    console.log('='.repeat(80));
    
    pages.forEach((page, index) => {
      console.log(`\n${index + 1}. ${page.name || 'Unnamed Page'} (ID: ${page.id})`);
      
      const components = page.components || [];
      console.log(`   Components: ${components.length}`);
      
      // Group components by type
      const componentTypes = {};
      components.forEach(comp => {
        const type = comp.component?.type || 'unknown';
        if (!componentTypes[type]) {
          componentTypes[type] = [];
        }
        componentTypes[type].push({
          name: comp.component?.name || 'Unnamed',
          label: comp.component?.label || '',
          text: comp.component?.text || ''
        });
      });
      
      Object.keys(componentTypes).forEach(type => {
        console.log(`   - ${type}: ${componentTypes[type].length}`);
        componentTypes[type].slice(0, 5).forEach(comp => {
          const displayName = comp.label || comp.name || comp.text || 'Unnamed';
          console.log(`     • ${displayName}`);
        });
        if (componentTypes[type].length > 5) {
          console.log(`     ... and ${componentTypes[type].length - 5} more`);
        }
      });
    });
    
    // Extract query information
    console.log('\n' + '='.repeat(80));
    console.log('QUERIES:');
    console.log('='.repeat(80));
    
    const queryTypes = {};
    queries.forEach(query => {
      const type = query.type || 'unknown';
      if (!queryTypes[type]) {
        queryTypes[type] = [];
      }
      queryTypes[type].push({
        name: query.name || 'Unnamed',
        resource: query.resource?.name || ''
      });
    });
    
    Object.keys(queryTypes).forEach(type => {
      console.log(`\n${type}: ${queryTypes[type].length} queries`);
      queryTypes[type].slice(0, 10).forEach(query => {
        console.log(`  - ${query.name}${query.resource ? ` (${query.resource})` : ''}`);
      });
      if (queryTypes[type].length > 10) {
        console.log(`  ... and ${queryTypes[type].length - 10} more`);
      }
    });
    
    // Extract resources/API endpoints
    const resources = appData.resources || [];
    if (resources.length > 0) {
      console.log('\n' + '='.repeat(80));
      console.log('RESOURCES/API ENDPOINTS:');
      console.log('='.repeat(80));
      resources.forEach(resource => {
        console.log(`- ${resource.name || 'Unnamed'}: ${resource.type || 'unknown'}`);
      });
    }
    
    console.log('\n' + '='.repeat(80));
    console.log('ANALYSIS COMPLETE');
    console.log('='.repeat(80));
    console.log('\nNext steps:');
    console.log('1. Review the pages and components listed above');
    console.log('2. Open Retool application and document each page in detail');
    console.log('3. Fill in RETOOL_UI_UX_ANALYSIS.md with specific details');
    console.log('4. Note any UX improvements to make in React version\n');
    
  } catch (error) {
    console.error('Error reading Retool JSON:', error.message);
    console.log('\nTroubleshooting:');
    console.log('1. Make sure Node.js is installed');
    console.log('2. Check that the JSON file exists and is valid');
    console.log('3. The file might be too large - try analyzing in sections');
  }
}

extractRetoolStructure();

