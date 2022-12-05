Welcome to Node Edge's documentation!
=====================================

This tool allows you to run Node code from Python, including dependency
management:

.. code-block::

    from node_edge import NodeEngine

    package = {
        "dependencies": {
            "axios": "^1.2.0",
        },
    }


    with NodeEngine(package) as ne:
        axios = ne.import_from("axios")
        print(axios.get("https://httpbin.org/robots.txt").data)


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   getting-started
   proxies
   performance
   contributing


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
