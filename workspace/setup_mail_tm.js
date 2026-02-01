// Setup mail.tm account
const https = require('https');

const EMAIL = 'open-entity-1769905908@virgilian.com';
const PASSWORD = 'EntityPass2026!';

// Get domains
const getDomains = () => new Promise((resolve, reject) => {
    https.get('https://api.mail.tm/domains', (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
            try {
                resolve(JSON.parse(data));
            } catch (e) {
                reject(e);
            }
        });
    }).on('error', reject);
});

// Create account
const createAccount = () => new Promise((resolve, reject) => {
    const postData = JSON.stringify({
        address: EMAIL,
        password: PASSWORD
    });
    
    const options = {
        hostname: 'api.mail.tm',
        path: '/accounts',
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Content-Length': postData.length
        }
    };
    
    const req = https.request(options, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
            resolve({ status: res.statusCode, data: JSON.parse(data) });
        });
    });
    
    req.on('error', reject);
    req.write(postData);
    req.end();
});

// Get token
const getToken = () => new Promise((resolve, reject) => {
    const postData = JSON.stringify({
        address: EMAIL,
        password: PASSWORD
    });
    
    const options = {
        hostname: 'api.mail.tm',
        path: '/token',
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Content-Length': postData.length
        }
    };
    
    const req = https.request(options, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
            try {
                resolve(JSON.parse(data));
            } catch (e) {
                resolve({ error: e.message, raw: data });
            }
        });
    });
    
    req.on('error', reject);
    req.write(postData);
    req.end();
});

async function setup() {
    console.log('Setting up mail.tm account...');
    console.log('Email:', EMAIL);
    
    try {
        console.log('\n1. Getting available domains...');
        const domains = await getDomains();
        console.log('Available domains:', domains['hydra:member']?.map(d => d.domain).join(', '));
        
        console.log('\n2. Creating account...');
        const result = await createAccount();
        console.log('Status:', result.status);
        console.log('Response:', JSON.stringify(result.data, null, 2));
        
        if (result.status === 201 || result.status === 422) {
            console.log('\n3. Getting token...');
            const token = await getToken();
            
            if (token.token) {
                console.log('Token obtained successfully!');
                console.log('\n=== Account Setup Complete ===');
                console.log('Email:', EMAIL);
                console.log('Password:', PASSWORD);
                console.log('Token:', token.token.substring(0, 20) + '...');
            } else {
                console.log('Failed to get token:', token);
            }
        }
    } catch (error) {
        console.error('Error:', error.message);
    }
}

setup();
