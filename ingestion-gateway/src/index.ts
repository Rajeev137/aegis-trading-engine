import WebSocket from 'ws';
import amqp from 'amqplib';
import http from 'http';
import { config } from 'dotenv';

config();

const RABBITMQ_URL = process.env.RABBITMQ_URL || 'amqp://guest:guest@rabbitmq:5672';

// Comma-separated list of Binance symbols to stream, e.g. "BTCUSDT,ETHUSDT,SOLUSDT"
// Each symbol maps to a pair published as "<BASE>-USD" (USDT treated as USD)
const RAW_PAIRS = (process.env.PAIRS || 'BTCUSDT').toUpperCase().split(',').map(s => s.trim());

// Build Binance combined stream URL: /stream?streams=btcusdt@trade/ethusdt@trade/...
const streams = RAW_PAIRS.map(s => `${s.toLowerCase()}@trade`).join('/');
const BINANCE_WS_URL = `wss://stream.binance.com:9443/stream?streams=${streams}`;

// true = RabbitMQ connected AND Binance WS open; flipped to false on any disconnect
let healthy = false;

// K8s liveness/readiness probe target — port 3000, path /
// Returns 200 when healthy, 503 when either upstream connection is down
http.createServer((_, res) => {
    if (healthy) {
        res.writeHead(200);
        res.end('ok');
    } else {
        res.writeHead(503);
        res.end('not ready');
    }
}).listen(3000);

// Convert Binance symbol (e.g. "BTCUSDT") to our pair format (e.g. "BTC-USD")
// Binance uses USDT but we normalise to USD throughout the system
function symbolToPair(symbol: string): string {
    const base = symbol.replace(/USDT$|BUSD$|USD$/, '');
    return `${base}-USD`;
}

async function startGateway() {
    try {
        console.log(`Connecting to RabbitMQ...`);
        const conn = await amqp.connect(RABBITMQ_URL);
        const channel = await conn.createChannel();

        const exchange = 'market-data';
        await channel.assertExchange(exchange, 'fanout', { durable: false });
        console.log(`Connected to RabbitMQ, exchange verified`);
        console.log(`Subscribing to pairs: ${RAW_PAIRS.join(', ')}`);

        conn.on('close', () => { healthy = false; console.log('RabbitMQ connection closed'); });
        conn.on('error', (err) => { healthy = false; console.error('RabbitMQ error:', err); });

        console.log(`Connecting to Binance combined stream...`);
        const ws = new WebSocket(BINANCE_WS_URL);

        ws.on('open', () => {
            healthy = true;
            console.log(`Connected to Binance — streaming: ${RAW_PAIRS.join(', ')}`);
        });

        ws.on('message', (data: string) => {
            // Combined stream wraps each event: { stream: "btcusdt@trade", data: { ... } }
            const envelope = JSON.parse(data);
            const trade = envelope.data;
            const price = parseFloat(trade.p);
            const pair = symbolToPair(trade.s); // trade.s is the symbol e.g. "BTCUSDT"

            const payload = JSON.stringify({ pair, price });
            channel.publish(exchange, '', Buffer.from(payload));

            if (Math.random() < 0.02) {
                console.log(`[Gateway] ${pair}: $${price.toFixed(2)}`);
            }
        });

        ws.on('error', (err) => { healthy = false; console.error('WebSocket error:', err); });
        ws.on('close', () => { healthy = false; console.log('WebSocket connection closed'); });

    } catch (error) {
        healthy = false;
        console.error('Gateway initialisation error:', error);
    }
}

startGateway();
