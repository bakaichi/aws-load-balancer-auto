# AWS Automation Script

This script automates the deployment of a highly available and scalable web application on AWS. It sets up a complete infrastructure that includes a VPC, subnets, an internet gateway, route tables, an EC2 instance, an Application Load Balancer, an Auto Scaling Group, and necessary security groups. It also configures a monitoring solution using CloudWatch.

## Features

- **VPC Creation**: Configures a Virtual Private Cloud with internet access.
- **EC2 Instance**: Deploys an EC2 instance with a web server and a sample Node.js application.
- **Load Balancing**: Sets up an Application Load Balancer that distributes incoming application traffic across multiple instances.
- **Auto Scaling**: Implements an Auto Scaling Group to handle changes in load.
- **Monitoring**: Uses CloudWatch for monitoring and alarming based on specific metrics like CPU utilization.
- **Security**: Configures security groups to allow HTTP and SSH traffic.

## Prerequisites

- AWS CLI installed and configured with appropriate permissions.
- Python 3.x.
- boto3 library installed (`pip install boto3`).
- Most recent ami for EC2

## Setup

1. **Clone the repository**:

2. **Install dependencies**:
```bash
pip install boto3
```
3. **Run Script**:
```bash
chmod +x mainScript.py
./mainScript.py
```



