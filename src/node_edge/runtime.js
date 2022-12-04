import net from "node:net";
import vm from "node:vm";

/**
 * This executes the JS code coming from Python.
 */
class Executor {
    constructor() {
        this.context = {};
        vm.createContext(this.context);
    }

    /**
     * Execute the code in the context and return the result.
     *
     * @param {string} code The code to execute.
     * @returns {any}
     */
    eval(code) {
        return vm.runInContext(code, this.context);
    }
}

class Handler {
    /**
     * @param {module:net.Socket} client Client socket, will send messages to it
     */
    constructor(client) {
        this.executor = new Executor();
        this.client = client;
    }

    /**
     * Sends a message back to the Python side
     *
     * @param {object} obj Any object that can be serialized to JSON
     */
    sendMessage(obj) {
        this.client.write(JSON.stringify(obj) + "\n");
    }

    /**
     * Serialize an error to a plain object.
     *
     * @param {Error} error An error object
     */
    serializeError(error) {
        return Object.fromEntries(
            Object.getOwnPropertyNames(error).map((key) => [key, error[key]])
        );
    }

    /**
     * Handles an eval event. If the code is valid, it will be executed and the
     * result will be sent back to the Python side. If the code is invalid, an
     * error will be sent back.
     *
     * @param {string} event_id The event ID
     * @param {string} code The code to execute
     */
    handleEval({ event_id, code }) {
        let result;
        console.log({ event_id, code });

        try {
            result = this.executor.eval(code);
            this.sendMessage({
                event_id,
                type: "eval_result",
                payload: {
                    result,
                },
            });
        } catch (error) {
            console.log(this);
            this.sendMessage({
                event_id,
                type: "eval_error",
                payload: {
                    error: this.serializeError(error),
                },
            });
        }
    }

    /**
     * Handles a message from the Python side.
     *
     * @param {string} line A line of JSON
     */
    handleLine(line) {
        let event;

        try {
            event = JSON.parse(line);
        } catch (e) {
            throw Error("Invalid JSON");
        }

        if (
            typeof event !== "object" ||
            event === null ||
            Array.isArray(event)
        ) {
            throw Error("Not an object");
        }

        if (event.type === "eval") {
            this.handleEval(event.payload);
        } else {
            throw Error("Unknown event type");
        }
    }
}

/**
 * Parse the command line arguments, which contain the port to connect to.
 *
 * @returns {{port: number}}
 */
function parseArgv() {
    const argv = process.argv.slice(2);

    if (argv.length !== 1) {
        throw Error("Expected exactly 1 argument");
    }

    const [portStr] = argv;
    const port = parseInt(portStr, 10);

    if (Number.isNaN(port)) {
        throw Error(`Port ${portStr} is not a number`);
    }

    return { port };
}

/**
 * Connect to the Python side and start handling messages.
 */
function main() {
    const args = parseArgv();
    const client = new net.Socket();
    const buf = [];
    const handler = new Handler(client);

    client.setEncoding("utf-8");
    client.connect({
        host: "::1",
        port: args.port,
    });

    client.on("data", function (data) {
        try {
            const lines = data.split("\n");

            if (lines.length === 1) {
                buf.push(data);
            } else {
                const firstLine = buf.join("") + lines[0];
                handler.handleLine(firstLine);

                for (const line of lines.slice(1, lines.length - 1)) {
                    handler.handleLine(line);
                }

                buf.length = 0;
                buf.push(lines[lines.length - 1]);
            }
        } catch (e) {
            client.destroy();
            console.error("Protocol error");
            console.error(e);
            process.exit(1);
        }
    });

    client.on("error", function (e) {
        console.error(e);
        process.exit(1);
    });

    client.on("end", function () {
        console.log("Connection lost, terminating");
        process.exit(0);
    });
}

main();
