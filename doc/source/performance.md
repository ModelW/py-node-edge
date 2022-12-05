# Performance

While Node Edge is made to be useful, it's not made to be fast. Obviously the
code that runs on Python side will run at Python speed and the one on Node side
will run at Node speed. But the communication between the two is not optimized
at all.

We'll review in this section all the different things that can go wrong.

## Memory

One important detail is that Node is sending "pointers" to Python so that
[Proxies](proxies.md) can be created. Those pointers are never freed. So if you
create a lot of them, you'll end up with a lot of memory usage.

There is currently no solution to this except to shut down the Node Edge engine
quickly after starting it and create a new one when you need it again.

## Startup time

This might however be difficult to do, because when you start the engine you
will implicitly run a `npm install` to get all the dependencies that you've
asked for.

And while it stays in cache, that takes a good 0.5s to run every time.

## Proxies

Those proxies are very convenient but each operation you do (get an attribute,
list the keys of a mapping, etc) will result in a round trip to Node. So if you
do something like `axios.get("https://httpbin.org/get").data` you'll end up
doing:

-   A trip to get `get`
-   A trip to call `get`
-   A trip to get `data`

Then however `data` will be serialized as JSON so you no longer need to
communicate with Node explore it further.

## Disk space

Every time you start the engine, it will create a directory containing the
environment. By default it's going to be in `$HOME/.local/state/node_edge` and
then every environment's name is a hash of the `package` specification you've
given.

There is no garbage collecting of those directories, so if you're running a lot
of different environments, you'll end up with a lot of disk space used. It's up
to you to clean those up.

On server environments where the `$HOME` directory is not really writable, it's
going to fall back to creating it in `/tmp` (or whatever the temporary directory
section is in your OS).
