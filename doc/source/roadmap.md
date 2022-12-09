# Roadmap

Let's have a look at the ideas and goals for the future versions.

This list shall evolve through time, especially as we get closer to each
revision its specifications should get more precise.

## 0.1

-   [x] **Basic functionality** &mdash; Being able to run Node code from Python
        while getting dependencies installed automatically
-   [ ] **Not too slow boot time** &mdash; Implementation of basic functionality
        showed that the boot time is quite high (0.5s) which is impractical for
        many applications. This needs to go down.
-   [ ] **Garbage collection** &mdash; When Python proxies get collected, the
        corresponding resources on the JS side should be freed as well.

## 0.2

-   [ ] **Install NPM deps through pip** &mdash; Today you need to declare Node
        dependencies when calling Node Edge. While this works, this requires to
        install dependencies at runtime and also prevents you from locking the
        dependencies the way you would for a normal Python package. NPM packages
        need to be proxied for Pip/Poetry/etc.
-   [ ] **Increased security** &mdash; Right now the binding happens through a
        socket. It would make sens to protect the communication between Python
        and Node better to avoid having a local attacker "stealing" the socket.

# 0.3

-   [ ] **Node binding instead of external process** &mdash; The initial
        implementation relies on Node being already installed on the system. It
        would be more interesting to ship Node directly with the Node Edge
        package and use a C binding to call it from the same process instead of
        running it in an outside process.
-   [ ] **No more context manager** &mdash; We'll drop the requirement to be
        used through a context manager. All should be transparent.

# 0.4

-   [ ] **Async support** &mdash; At this stage the requirements for an API will
        be well-understood. It will be the time to refactor everything and offer
        both a sync and an async API.

# 0.5

-   [ ] **TypeScript-based typed proxies** &mdash; TypeScript packages should be
        accessible through generated proxies with valid type annotations.

# 1.0

-   [ ] **Comprehensive documentation** &mdash; Any gaps in the documentation
        should be filled.
-   [ ] **Stable API** &mdash; The API should be stable and not change anymore.
