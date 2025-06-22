import ray

class RayContainer:
    def __init__(self, address: str = None, **kwargs):
        self.ray = None
        self.ray_init_kwargs = {}
        self.ray_shutdown = False
        self.init_ray(**kwargs)
        self.connect_to_ray(address)

    def init_ray(self, **kwargs):
        """Initialize Ray with the given keyword arguments."""
        if self.ray is None:
            self.ray = ray
            self.ray_init_kwargs = kwargs
            self.ray.init(**kwargs)
        else:
            print("Ray is already initialized.")

    def connect_to_ray(self, address: str):
        """Connect to an existing Ray cluster."""
        if self.ray is None:
            self.ray = ray
        self.ray.init(address=address)

    def shutdown_ray(self):
        """Shutdown the Ray instance if it was initialized by this container."""
        if self.ray is not None and not self.ray_shutdown:
            self.ray.shutdown()
            self.ray = None
            self.ray_shutdown = True
        else:
            print("Ray is either not initialized or already shutdown.")