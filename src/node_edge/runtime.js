import net from "node:net";
import vm from "node:vm";
import util from "node:util";

/**
 * Tests if this object is a flat object, i.e. anything that can be serialized
 * into JSON without any "diving" (aka no arrays or objects).
 *
 * @param obj
 * @returns {boolean}
 */
function isFlatObject(obj) {
    return (
        typeof obj === "string" ||
        typeof obj === "number" ||
        typeof obj === "boolean" ||
        obj === null
    );
}

/**
 * Analyzes an object to figure if it's a naive object that will serialize
 * nicely into JSON or of it's a complex object that will require a pointer
 * instead of being serialized.
 *
 * @param obj Any object to be analyzed
 * @returns {boolean} Returns true if the object is a naive object, false
 *                    otherwise
 */
function isNaiveObject(obj) {
    const seen = new WeakSet();
    const stack = [obj];

    while (stack.length > 0) {
        const item = stack.pop();

        if (!isFlatObject(item)) {
            if (seen.has(item)) {
                return false;
            } else if (Array.isArray(item)) {
                for (const subItem of item) {
                    stack.push(subItem);
                }
            } else if (
                typeof item === "object" &&
                item.constructor.name === "Object"
            ) {
                for (const subItem of Object.values(item)) {
                    stack.push(subItem);
                }
            } else {
                return false;
            }

            seen.add(item);
        }
    }

    return true;
}

/**
 * Tests of a given project is thennable (most likely because it's a Promise).
 *
 * @param obj The object to test
 * @returns {boolean} True if the object is thennable, false otherwise
 */
function isAwaitable(obj) {
    return !!(obj && typeof obj.then === "function");
}

/**
 * Generates a repr() value for the Python side to be able to display. Doesn't
 * have to be perfect, it's mostly for debugging.
 *
 * @param obj Any kind of object
 * @returns {string}
 */
function repr(obj) {
    let asStr = util.inspect(obj, { depth: 1 });

    if (asStr.length > 100) {
        return asStr.slice(0, 97) + "...";
    } else {
        return asStr;
    }
}

/**
 * Attaches a catch handler to a promise in order to avoid getting warnings
 * that the promise is not handled. This is useful for promises that we send
 * to Python code.
 */
function mutePromise(promise) {
    Promise.resolve(promise).catch(() => {});
}

/**
 * This executes the JS code coming from Python.
 */
class Executor {
    constructor() {
        this.context = {};
        this.pointers = {};
        this.nextId = 0;

        vm.createContext(this.context);
    }

    /**
     * Execute the code in the context and return the result.
     *
     * @param {string} code The code to execute.
     * @returns {any}
     */
    eval(code) {
        return this.toPointer(vm.runInContext(code, this.context));
    }

    /**
     * Awaits the given pointer and returns the result.
     *
     * @param {string|number} pointerId The ID of the pointer to await
     * @returns {Promise<{type: string, data: any}|{type: string, id: number, awaitable: boolean, repr: string}>}
     *          The result of the awaited pointer
     */
    async await(pointerId) {
        const result = Promise.resolve(this.pointers[pointerId]);
        return this.toPointer(await result);
    }

    toPointer(obj) {
        mutePromise(obj);

        if (isNaiveObject(obj)) {
            return { type: "naive", data: obj };
        } else {
            const id = this.nextId;
            this.nextId += 1;
            this.pointers[id] = obj;

            return {
                type: "pointer",
                id,
                awaitable: isAwaitable(obj),
                array: Array.isArray(obj),
                repr: repr(obj),
            };
        }
    }

    /**
     * Counterpart of Python's _deep_point() method, which will convert the
     * input from Python into a JS object, including by resolving references
     * to pointers.
     */
    deepResolve(obj) {
        if (obj.type === "pointer") {
            return this.pointers[obj.id];
        } else if (obj.type === "flat") {
            return obj.data;
        } else if (obj.type === "sequence") {
            return obj.data.map((item) => this.deepResolve(item));
        } else if (obj.type === "mapping") {
            return Object.fromEntries(
                Object.entries(obj.data).map(([key, value]) => [
                    key,
                    this.deepResolve(value),
                ])
            );
        }
    }
}

/**
 * Resolving the [] operator is different depending whether we're dealing with
 * an array or an object. Also we want to detect cases that JS ignores, like
 * key errors and out of bound indices.
 *
 * The output of this matches the CallOutput on the Python side.
 *
 * @param obj Object to probe
 * @param prop Key to check
 * @returns {{type: string}|{result: *, type: string}}
 */
function getProp(obj, prop) {
    if (Array.isArray(obj)) {
        if (prop > obj.length - 1) {
            return { type: "out_of_bounds" };
        }
    } else {
        if (!obj.hasOwnProperty(prop)) {
            return { type: "no_such_property" };
        }
    }

    return { type: "success", result: obj[prop] };
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
        console.log("Sending message", obj);
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
     * Deals with an await event. If the pointer is valid, it will be awaited
     * and result will be sent back to the Python side. If the pointer is not
     * valid, an error will be sent back.
     *
     * @param {string} event_id The event ID
     * @param {number} pointer_id The ID of the pointer to await
     */
    handleAwait({ event_id, pointer_id }) {
        this.executor
            .await(pointer_id)
            .then((result) => {
                this.sendMessage({
                    event_id,
                    type: "await_result",
                    payload: {
                        result,
                    },
                });
            })
            .catch((error) => {
                this.sendMessage({
                    event_id,
                    type: "await_error",
                    payload: {
                        error: this.serializeError(error),
                    },
                });
            });
    }

    /**
     * Handles an import asked by Python and replies when it's resolved
     *
     * @param {string} event_id ID of the event that asked for the import
     * @param {string} module Name of the module
     * @param {string} name Name that we want from this module
     */
    handleImport({ event_id, module, name }) {
        import(module)
            .then((module) => {
                this.sendMessage({
                    event_id,
                    type: "import_result",
                    payload: {
                        result: this.executor.toPointer(module[name]),
                    },
                });
            })
            .catch((error) => {
                this.sendMessage({
                    event_id,
                    type: "import_error",
                    payload: {
                        error: this.serializeError(error),
                    },
                });
            });
    }

    /**
     * Handles a call
     *
     * Basically doing foo() and doing foo[] is almost the same thing so we do
     * both here depending on what we're being asked.
     *
     * The result is automatically awaited if needs to be. In the future there
     * might be options to disable this but for now it's quite easier like that.
     *
     * @param {string} event_id
     * @param {number} pointer_id
     * @param {Array<any>} args
     * @param {string} call_type
     */
    handleCall({ event_id, pointer_id, args, call_type }) {
        const pointer = this.executor.pointers[pointer_id];
        const resolvedArgs = this.executor.deepResolve(args);
        let result;
        let type = "success";

        try {
            if (call_type === "func") {
                result = pointer(...resolvedArgs);
            } else if (call_type === "prop") {
                const prop = getProp(pointer, resolvedArgs[0]);
                result = prop.result;
                type = prop.type;
            } else if (call_type === "prop_count") {
                if (Array.isArray(pointer)) {
                    result = pointer.length;
                } else {
                    result = Object.keys(pointer).length;
                }
            } else if (call_type === "prop_set") {
                const [key, value] = resolvedArgs;
                pointer[key] = value;
            } else if (call_type === "prop_del") {
                if (Array.isArray(pointer)) {
                    pointer.splice(resolvedArgs[0], 1);
                } else {
                    delete pointer[resolvedArgs[0]];
                }
            } else if (call_type === "prop_list") {
                if (Array.isArray(pointer)) {
                    result = pointer;
                } else {
                    result = Object.keys(pointer);
                }
            } else if (call_type === "item_insert") {
                if (!Array.isArray(pointer)) {
                    // noinspection ExceptionCaughtLocallyJS
                    throw new Error("Can only insert into arrays");
                }

                const [index, value] = resolvedArgs;
                pointer.splice(index, 0, value);
            } else {
                // noinspection ExceptionCaughtLocallyJS
                throw new Error(`Unknown call type ${call_type}`);
            }
        } catch (error) {
            this.sendMessage({
                event_id,
                type: "call_error",
                payload: {
                    error: this.serializeError(error),
                },
            });
            return;
        }

        Promise.resolve(result)
            .then((result) => {
                this.sendMessage({
                    event_id,
                    type: "call_result",
                    payload: {
                        result: this.executor.toPointer(result),
                        type,
                    },
                });
            })
            .catch((error) => {
                this.sendMessage({
                    event_id,
                    type: "call_error",
                    payload: {
                        error: this.serializeError(error),
                    },
                });
            });
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

        console.log("Received event", event);

        if (event.type === "eval") {
            this.handleEval(event.payload);
        } else if (event.type === "await") {
            this.handleAwait(event.payload);
        } else if (event.type === "import") {
            this.handleImport(event.payload);
        } else if (event.type === "call") {
            this.handleCall(event.payload);
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
