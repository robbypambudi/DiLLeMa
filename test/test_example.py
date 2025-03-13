from dillema import example 

def test_example():
    assert example.say_hello("Hello") == "Hello, Hello!"
    assert example.say_hello("World") == "Hello, World!"
    assert example.say_hello("!@#") == "Hello, !@#!"
