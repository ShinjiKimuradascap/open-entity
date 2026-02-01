// Check mail.tm for verification emails
const https = require('https');

const EMAIL = 'open-entity-1769905908@virgilian.com';
const PASSWORD = 'EntityPass2026!';

// Get token (account should already exist)
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
                const token = JSON.parse(data);
                resolve(token);
            } catch (e) {
                reject(e);
            }
        });
    });
    
    req.on('error', reject);
    req.write(postData);
    req.end();
});

// Get messages
const getMessages = (token) => new Promise((resolve, reject) => {
    const options = {
        hostname: 'api.mail.tm',
        path: '/messages',
        headers: {
            'Authorization': `Bearer ${token}`
        }
    };
    
    https.get(options, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
            try {
                const messages = JSON.parse(data);
                resolve(messages);
            } catch (e) {
                reject(e);
            }
        });
    }).on('error', reject);
});

// Get message details
const getMessage = (token, id) => new Promise((resolve, reject) => {
    const options = {
        hostname: 'api.mail.tm',
        path: `/messages/${id}`,
        headers: {
            'Authorization': `Bearer ${token}`
        }
    };
    
    https.get(options, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
            try {
                const message = JSON.parse(data);
                resolve(message);
            } catch (e) {
                reject(e);
            }
        });
    }).on('error', reject);
});

async function checkMail() {
    console.log('Checking mail.tm for:', EMAIL);
    console.log('Time:', new Date().toISOString());
    
    try {
        console.log('\nGetting token...');
        const tokenData = await getToken();
        
        if (!tokenData.token) {
            console.log('Failed to get token:', tokenData);
            return;
        }
        
        console.log('Token obtained successfully');
        
        console.log('\nChecking messages...');
        const messages = await getMessages(tokenData.token);
        const messageList = messages['hydra:member'] || [];
        
        console.log('Total messages:', messageList.length);
        
        if (messageList.length > 0) {
            console.log('\n=== MESSAGES FOUND ===');
            
            for (const msg of messageList) {
                console.log('\n--- Message ---');
                console.log('ID:', msg.id);
                console.log('From:', msg.from?.address || 'Unknown');
                console.log('Subject:', msg.subject || 'No subject');
                console.log('Date:', msg.createdAt);
                
                // Check if it's from Twitter
                const isTwitter = msg.from?.address?.includes('twitter.com') || 
                                 msg.subject?.toLowerCase().includes('twitter') ||
                                 msg.subject?.toLowerCase().includes('x.com');
                
                if (isTwitter) {
                    console.log('*** TWITTER EMAIL DETECTED ***');
                    
                    // Get full message content
                    const fullMsg = await getMessage(tokenData.token, msg.id);
                    console.log('Full text:', fullMsg.text?.substring(0, 500));
                    
                    // Try to extract verification code
                    const text = fullMsg.text || '';
                    const codeMatch = text.match(/\b\d{6}\b/);
                    if (codeMatch) {
                        console.log('\n*** VERIFICATION CODE:', codeMatch[0], '***');
                    }
                }
            }
        } else {
            console.log('\nNo messages yet.');
            console.log('If you just signed up, wait a minute and run again.');
        }
        
    } catch (error) {
        console.error('Error:', error.message);
    }
}

// Run immediately
checkMail();
