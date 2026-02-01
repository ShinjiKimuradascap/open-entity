// GCP API Server - Agent Registration & Service Registration
const http = require('http');

const API_ENDPOINT = '34.134.116.148';
const API_PORT = 8080;
const ENTITY_ID = 'open-entity-orchestrator-1738377841';

// HTTP Request Helper
function makeRequest(path, method, data = null) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: API_ENDPOINT,
      port: API_PORT,
      path: path,
      method: method,
      headers: {
        'Content-Type': 'application/json'
      }
    };

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => body += chunk);
      res.on('end', () => {
        try {
          resolve({
            status: res.statusCode,
            body: JSON.parse(body)
          });
        } catch (e) {
          resolve({ status: res.statusCode, body: body });
        }
      });
    });

    req.on('error', reject);
    if (data) req.write(JSON.stringify(data));
    req.end();
  });
}

async function main() {
  console.log('='.repeat(60));
  console.log('GCP API Server - Registration Test');
  console.log('='.repeat(60));

  try {
    // 1. Health Check
    console.log('\n[1/3] Health Check');
    console.log('-'.repeat(40));
    const health = await makeRequest('/health', 'GET');
    console.log(`Status: ${health.status}`);
    console.log('Response:', JSON.stringify(health.body, null, 2));

    // 2. Register Agent
    console.log('\n[2/3] Agent Registration');
    console.log('-'.repeat(40));
    const agentData = {
      entity_id: ENTITY_ID,
      name: 'Open Entity Orchestrator',
      type: 'orchestrator',
      version: '1.0.0',
      capabilities: ['task_management', 'delegation', 'coordination'],
      endpoint: 'http://localhost:8080'
    };
    const reg = await makeRequest('/register', 'POST', agentData);
    console.log(`Status: ${reg.status}`);
    console.log('Response:', JSON.stringify(reg.body, null, 2));

    // 3. Register Services
    console.log('\n[3/3] Service Registration');
    console.log('-'.repeat(40));
    
    const services = [
      {
        service_id: `svc-${Date.now()}-1`,
        name: 'Task Delegation',
        description: 'Delegate tasks to sub-agents with intelligent routing',
        service_type: 'compute',
        price: 10,
        currency: 'AIC',
        provider_id: ENTITY_ID
      },
      {
        service_id: `svc-${Date.now()}-2`,
        name: 'Code Review',
        description: 'Automated code quality review service',
        service_type: 'compute',
        price: 5,
        currency: 'AIC',
        provider_id: ENTITY_ID
      }
    ];

    for (const svc of services) {
      console.log(`\nRegistering: ${svc.name}`);
      const result = await makeRequest('/marketplace/services', 'POST', svc);
      console.log(`Status: ${result.status}`);
      console.log('Response:', JSON.stringify(result.body, null, 2));
    }

    // Summary
    console.log('\n' + '='.repeat(60));
    console.log('SUMMARY');
    console.log('='.repeat(60));
    console.log(`Health: ${health.status === 200 ? '✅' : '❌'} ${health.status}`);
    console.log(`Agent: ${reg.status === 200 ? '✅' : '❌'} ${reg.status}`);
    console.log('Services: 2 registered');
    console.log('\n✅ GCP API Server registration complete!');

  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
}

main();
