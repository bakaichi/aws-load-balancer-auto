#!/usr/bin/env python3

with open('config.txt', 'r') as f:
    load_balancer_dns = f.read().strip()

from locust import HttpUser, task, between

class MyUser(HttpUser):
    wait_time = between(1, 5)  
    host = f"http://{load_balancer_dns}"  

    @task
    def hit_load_balancer(self):
        self.client.get("/login")