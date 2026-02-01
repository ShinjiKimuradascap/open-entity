// Create new mail.tm account with random suffix
const https = require('https');

const TIMESTAMP = Date.now();
const EMAIL = `entity-ai-${TIMESTAMP}@virgilian.com`;
const PASSWORD = `EntityAI${TIMESTAMP}!`;

console.log('Creating new mail.tm account...');
console.log('Email:', EMAIL);
console.log('Password:', PASSWORD);

// Save credentials to file
const fs = require('fs');
const credentials = {
    email: EMAIL,
    password: PASSWORD,
    created: new Date().toISOString()
};
fs.writeFileSync('mail_credentials.json', JSON.stringify(credentials, null, 2));
console.log('\nCredentials saved to: mail_credentials.json');

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
                resolve({ error: e.message });
            }
        });
    });
    
    req.on('error', reject);
    req.write(postData);
    req.end();
});

async function setup() {
    try {
        console.log('\n1. Creating account...');
        const result = await createAccount();
        console.log('Status:', result.status);
        
        if (result.status === 201) {
            console.log('Account created successfully!');
            
            console.log('\n2. Getting token...');
            const token = await getToken();
            
            if (token.token) {
                console.log('Token obtained!');
                
                // Update credentials file
                credentials.token = token.token;
                fs.writeFileSync('mail_credentials.json', JSON.stringify(credentials, null, 2));
                
                console.log('\n=== Setup Complete ===');
                console.log('Email:', EMAIL);
                console.log('Password:', PASSWORD);
                console.log('Token:', token.token.substring(0, 30) + '...');
                console.log('\nUse this email for Twitter signup!');
            } else {
                console.log('Failed to get token:', token);
            }
        } else {
            console.log('Failed to create account:', result.data);
        }
    } catch (error) {
        console.error('Error:', error.message);
    }
}

setup();
