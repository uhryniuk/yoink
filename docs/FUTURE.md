Hello Claudy!

# Vision

A Python-based web scraping library that includes a CLI AND a webservice.

The goal being a fast, fault-tolerant and efficient way to scrape web dynamic web pages (that includes static pages if no JS has to load). This means that if our request fails, we have built-in sensible retries, we use playwright with multiprocessing AND asyncio per core to ensure we have an absolutely bonkers scrape rate. I should be able to provide a list of 1000 URLs, and set the numbers of workers (num of cores) and it'll churn through those as fast as possible, recovering where failures are encountered. Yoink is also mindful about Network I/O too, I don't want to get into a scenario where we make so many requests that we saturate I/O and start failing either. Cores or memory may be our limiting factor according to amdahls law but we'll see.

I should mention that I want this to be the backbone of a SaaS that I am starting (extract as a Service), so be mindful of that. Do not mention that in the project, as I will have private repos to work on that project but this will be a core piece of it, including the webservice (which I intend to extend privately).

## Core components

Below are the core partss of the system with details included in each of them. There is a semi-dependent chain here where each subsequent section depends on the previous a bit. Consider all of these holistically though, as when we actually build a implementation plan, that's where we will outline pure dependencies.

### extract Engine

The scaper engine will be the "private" code in the python libary. It will be something users will not directly extend.

CLAUDE: (tell me if this sounds like a bad design)

The core design of will be the scraping reconciler. The reconciler consists of a polling loop and the fundemental purpose is to work with the extract worker pool and the url queue.

The worker pool, will vary in size based on the number of workers being set. Each worker will run an instace of playwright in a seperate core using multiprocessing, and each instance of palywright will be async to have that awesome performance gainz we looking for here. Each worker will maintain it's own url queue, the workers never have to sit idle and there should be a size variable that corresponds to the worker queue. 

The url queue will be a process-safe, thread-safe queue (essentially an atomic queue) that we can essentially add to from anywhere in our program. The queue is not bounded, so it can continually accept new inputs. The queue will accept various types such as a url, extract request (scraper request being the base most type), and anything else that extends the ScraperRequest. The queue will then iterate over all of the available workers, and if there is space in their queue, they will continually be topped up. This way, the workers aren't ever idle as long as new urls are being added to them. To clarify, the queue accepts a number of different types, all of which must extend the ScraperRequest class. The workers will accept new work in their individual queues, assuming they are `isinstance(obj, ExtractReq)`.

The extract request is the fundemental unit of work that we pass around in our backend code, it will also be a part of the public API as well. It includes the URL to scrape of course but can also include other options such as retry strategies, or other configurations. These retry strategies and other configurations are then used on a per request basis to the. 

Ideally, the extraction engine can be started with a single, yoink.Engine().start(cfg). Where a part of the reconciler loop, we will continually check if the configuration has changed and apply those options.


### Python library API

The Python library API should be relatively small. We should provide interfaces then a few functions to run it all. Ideally, the user could `pip install yoink`, then run `python -c "import yoink; raw_html = yoink.get('https://some.url')"`. Alternatively, yoink.get_all([]), to get a bunch of different urls using the default scraping settings.

We should also expose the yoink extract engine, so users could create multiple instances of it if they would like to (for isolation or to manage seperate queues for some reason).

CLAUDE: It'd be helpfuk if you suggest additional ways we could extend the API to make it helpful here. Ideally, use existing apis from other librries to gain inspiration for what good design might look like.


### FastAPI service

We want to use FastAPI for it's simplicity, adoption and speed.

The service should be relatively straight forward. We may want some endpoints that do the following:

- /extract: Should accept an extract request and return it
- /config: Get only to display the configuration that is being run currently
- /status: Should report statistics (queue size, average time each extractoin takes, and anything other that is useful)
- /health: is the service okay, basic check.
- Any others that would be helpful here!


### Additional

#### Logging

I want this to use strucutured logging, writing jsonl lines to stdout. The oneline config options should be for the log level to filter on and to only includes jsonl with timestamp and msg (dropping all other contextul info so it's easier to read).

#### Configs

We should have a base config, perhaps just Config that also contains nested conigs. Nested configs could be for the workers, so we could have a WorkerConfig or any other subsystem that might need it's own dedicated settings.

We want configs to be able to be provided with the --config flag, in toml format, and be able to parse nested configs as needed. We also want to look for a default config in the XDG config directory. Additionally, we should be able to use env vars to specify our config options so YK_CONFIG="path/to/config".


#### ExtractReq and other musings

Does the idea of an extract request make sense? Is there a better approach to this? The idea was the the extraction request could contain configs to use on a per url basis, then we extend that to create requests for specific sites or for specific workflow.

ExtractReq should also ideally map really easily to json, with the idea being when we implement the service, this concept directly maps over. So all web service requests should be valid (or parsed as such) ExtractReq.

#### Implementation Manifest

- Try to use as few dependencies as possible

- Our cli tool should have 2 names, yoink and yk, so we could do yk "https://some.url"

- How could agents or AI usage be used in here more? Like how could we make our api extensible so we can have manage the lifecycle of scraping but as we scrape, we can easily send that context to agents/llms?

## priority

We have a lot of different parts of the system here, so here is some explicit priority to follow in the design of it:

1. Extract Engine: The heart of the machine, this needs to be our rock solid base?

2. Web Service: This is designed to be a proper scraping engine service, something we start, it has api keys or some other simple uath concept, and it's intended use is for an internal service, not something you'd expose to the internet.

3. Python Library: This goes hand in hand with Web Service, but we don't want to limit the web service to only using public api code. Howeever, our public api code surface should be small, simple and intuitive and ideally work really well programatically.
    - An example user story would be: The usre creates an instance of an engine, they only scrape intermitently, say every 30mins-6hours. We should be able to shutdown our playwright browser after some time of inactivity to ensure we aren't just wasting resources with it.

4. CLI: This is really an after thought, the command surface should be low but it should work with pipes very easily and make it easy to accept a JSON list of urls, throught stdin, then extract and write the results to stdout as json. or, we accept a arg with a json file then use those or we could provide the --stream option to continously write results to stdout as jsonl lines. Of course, we should have a command to start the service too! like `yoink serve`.
