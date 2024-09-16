from contextlib import ExitStack

class Check:
    def __init__(self, name : str, condition : str, channels : dict = None, description : str = ""):
        self.name = name

        if channels is None:
            channels = {}
            self.channels = {}
        else:
            self.channels = {k.replace(" ", ""): v for k, v in channels.items()} # erase the spaces in the channel names

        self.condition = condition
        for ch in channels.keys():
            self.condition = self.condition.replace(ch, ch.replace(" ", "")) # erase the spaces in the channel names
        try:
            self.code = compile(self.condition, "<string>", "eval")
        except SyntaxError as e:
            # print(f"Check '{self.name}': syntax error in '{self.condition}'")
            self.code = None

        self.description = description
        self.active = True

    def is_available(self):
        return self.active and (self.code is not None)

    def set_active(self, active : bool):
        self.active = active

    def set_channels(self, channels : dict):
        self.channels = {k.replace(" ", ""): v for k, v in channels.items()}
        for ch in channels.keys():
            self.condition = self.condition.replace(ch, ch.replace(" ", ""))
        try:
            self.code = compile(self.condition, "<string>", "eval")
        except SyntaxError as e:
            print(f"Check '{self.name}': syntax error in '{self.condition}'")
            self.code = None

    def eval_condition(self):
        if not self.active:
            return True
        if self.code is None:
            print(f"Check '{self.name}': syntax error in '{self.condition}'")
            return False

        # add all the channels attributes to the allowed objects
        channels = self.channels.copy()
        allowed_objects = {"abs", "int", "float", "str", "bool"}
        allowed_objects.update(channels.keys())
        for ch in channels.values():
            ch_attr = [attr for attr in dir(ch) if not attr.startswith("_")]
            allowed_objects.update(ch_attr)
        #print(allowed_objects)
        #print(self.code.co_names)
        # safe usage of eval using a restricted set of objects
        for name in self.code.co_names:
            if name not in allowed_objects:
                raise NameError(f"Check '{self.name}': name '{name}' in '{self.condition}' is not defined")
        return eval(self.code, {"__builtins__": {"abs":abs, "int":int, "float":float, "str":str, "bool":bool}}, channels)

    def simulate_eval_condition(self, channels_values : dict ):
        condition_replaced = self.condition
        for ch, val in channels_values.items():
            condition_replaced = condition_replaced.replace(ch, str(val))
        
        code = compile(condition_replaced, "<string>", "eval")

        return eval(code, {"__builtins__": {"abs":abs, "int":int, "float":float, "str":str, "bool":bool}}, self.channels.copy())

    
    def eval_condition_with_action(self):
        pass


# if the condition combines channels of different devices, we need to acquire the locks of these devices before evaluating the condition
class MultiDeviceCheck(Check):
    def __init__(self, name : str, condition : str, channels : dict = None, devices_locks : tuple = None, description : str = ""):
        super().__init__(name, condition, channels, description)
        if devices_locks is None:
            devices_locks = ()
        self.devices_locks = devices_locks

    def set_devices(self, devices_locks : tuple):
        self.devices_locks = devices_locks

    def eval_condition(self):
        # ExitStack allows us to manage a dynamic number of context managers
        with ExitStack() as stack:
            # Acquire all locks
            for lock in locks:
                stack.enter_context(lock)
            # Once all locks are acquired, perform the action
            rtrn = super().eval_condition()
        
        return rtrn
    
    def simulate_eval_condition(self, channels_values : dict):
        # ExitStack allows us to manage a dynamic number of context managers
        with ExitStack() as stack:
            # Acquire all locks
            for lock in locks:
                stack.enter_context(lock)
            # Once all locks are acquired, perform the action
            rtrn = super().simulate_eval_condition(channels_values)
        
        return rtrn


    def eval_condition_with_action(self):
        pass
