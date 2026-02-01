// Try different passwords for mail.tm
const https = require('https');

const EMAIL = 'open-entity-1769905908@virgilian.com';

// Common passwords to try
const PASSWORDS = [
    'TempPass123!',
    'EntityPass2026!',
    'Password123!',
    'OpenEntity2026!',
    'tempmail123',
    'virgilian123'
];

// Get token
const getToken = (password) => new Promise((resolve, reject) => {
    const postData = JSON.stringify({
        address: EMAIL,
        password: password
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
                const result = JSON.parse(data);
                resolve({ status: res.statusCode, data: result });
            } catch (e) {
                resolve({ status: res.statusCode, error: e.message, raw: data });
            }
        });
    });
    
    req.on('error', (e) => resolve({ error: e.message }));
    req.write(postData);
    req.end();
});

async function tryLogin() {
    console.log('Trying to login to mail.tm...');
    console.log('Email:', EMAIL);
    
    for (const password of PASSWORDS) {
        console.log(`\nTrying password: ${password}`);
        const result = await getToken(password);
        
        if (result.data?.token) {
            console.log('SUCCESS! Token obtained:');
            console.log('Password:', password);
            console.log('Token:', result.data.token.substring(0, 30) + '...');
            return;
        } else {
            console.log('Failed:', result.data?.message || result.error || 'Unknown error');
        }
    }
    
    console.log('\nAll passwords failed. The account may need to be recreated.');
}

tryLogin();
