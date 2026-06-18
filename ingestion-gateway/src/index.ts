import WebSocket from 'ws';
import amqp from 'amqplib';
import { config } from 'dotenv';

config();

const RABBITMQ_URL = process.env.RABBITMQ_URL || 'amqp://guest:guest@rabbitmq:5672'
// We will use Binance's public live trade stream for BTC/USDT
const BINANCE_WS_URL = 'wss://stream.binance.com:9443/ws/btcusdt@trade';

async function startGateway() {
    try {
        console.log('Connecting to RabbitMQ...');
        const conn = await amqp.connect(RABBITMQ_URL);
        const channel = await conn.createChannel();

        //we use 'fanout' exchange so multiple consumers can receive the same message if we scale up
        const exchange = 'market-data'
        await channel.assertExchange(exchange, 'fanout', { durable: false })
        console.log('Connected to RabbitMQ, exchange verified');

        console.log('Connecting to Binance WebSocket...')
        const ws = new WebSocket(BINANCE_WS_URL);

        ws.on('open', () => {
            console.log('Connected to Binance live stream');
        })
        ws.on('message', (data: string) => {
            // Each message is a trade event, we can parse it and publish to RabbitMQ
            const trade = JSON.parse(data);
            const price = parseFloat(trade.p) //'p' is the price field in Binance's trade event

            const payload = JSON.stringify({ pair: 'BTC-USD', price: price});

            //fire and forget RabbitMQ
            channel.publish(exchange, '', Buffer.from(payload));

            //log every 50th message just we dont spam the console
            if (Math.random() < 0.02){
                console.log(`[Gateway] Pushed Live BTC Price: $${price.toFixed(2)}`) 
            }
        })
        ws.on('error', (err) => console.error('WebSocket error:', err));
        ws.on('close', () => console.log('WebSocket connection closed'));

    }
    catch (error) {
        console.error('Gateway Initialiation error:', error);
    }
}

startGateway();
