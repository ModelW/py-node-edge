# Performance

While Node Edge is made to be useful, it's not made to be fast. Obviously the
code that runs on Python side will run at Python speed and the one on Node side
will run at Node speed. But the communication between the two is not optimized
at all.

We'll review in this section all the different things that can go wrong.

## Startup time

A node process needs to be started every time you create a NodeEngine instance.
This always takes a bit of time, count about 30ms.

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

```{note}
When some proxy gets garbage-collected, it will send a message to Node to
release the reference to the object. This is done to avoid memory leaks.
But it will also occupy the communication channel and slow down operations.
```

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
