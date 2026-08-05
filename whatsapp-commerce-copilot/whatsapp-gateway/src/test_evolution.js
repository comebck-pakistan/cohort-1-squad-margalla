const axios = require('axios');
const api = axios.create({
  baseURL: 'http://localhost:8081',
  headers: {
    'Content-Type': 'application/json',
    'apikey': 'evo-dev-key',
  }
});
api.post('/message/sendText/demo-store-shoes', {
  number: "923469357349",
  text: "Hello from test script via 8081",
  delay: 1200
}).then(res => console.log(res.data)).catch(err => console.error(err.response?.data || err.message));
