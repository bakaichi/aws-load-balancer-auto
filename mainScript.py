#!/usr/bin/env python3

import boto3
import time
import base64

# Create both EC2 resource and client
print("🔧 Creating AWS resources and clients...")
ec2 = boto3.resource('ec2')
ec2_client = boto3.client('ec2')
elb = boto3.client('elbv2')
asg = boto3.client('autoscaling')
cloudwatch = boto3.client('cloudwatch')

# Variables
ami_id = 'ami-04e5276ebb8451442'  
key_name = 'hdip244'
instance_tag = 'Master Avatar App'
ami_tag = 'Avatar App'

# Create a VPC
print("🌐 Creating VPC, Gateway, Route Table and Public Subnets...")
vpc = ec2.create_vpc(CidrBlock='10.0.0.0/16')
vpc.create_tags(Tags=[{'Key': 'Name', 'Value': 'MasterVPC'}])
vpc.wait_until_available()

# Create an Internet Gateway and attach it to the VPC
internet_gateway = ec2.create_internet_gateway()
vpc.attach_internet_gateway(InternetGatewayId=internet_gateway.id)

# Create a route table and a public route
route_table = vpc.create_route_table()
route_table.create_route(
    DestinationCidrBlock='0.0.0.0/0',
    GatewayId=internet_gateway.id
)

# Create public subnets and enable auto-assign public IP
subnet1 = vpc.create_subnet(CidrBlock='10.0.1.0/24', AvailabilityZone='us-east-1a')
subnet1.create_tags(Tags=[{'Key': 'Name', 'Value': 'PublicSubnet1'}])
ec2_client.modify_subnet_attribute(SubnetId=subnet1.id, MapPublicIpOnLaunch={'Value': True})

subnet2 = vpc.create_subnet(CidrBlock='10.0.2.0/24', AvailabilityZone='us-east-1b')
subnet2.create_tags(Tags=[{'Key': 'Name', 'Value': 'PublicSubnet2'}])
ec2_client.modify_subnet_attribute(SubnetId=subnet2.id, MapPublicIpOnLaunch={'Value': True})

subnet3 = vpc.create_subnet(CidrBlock='10.0.3.0/24', AvailabilityZone='us-east-1c')
subnet3.create_tags(Tags=[{'Key': 'Name', 'Value': 'PublicSubnet3'}])
ec2_client.modify_subnet_attribute(SubnetId=subnet3.id, MapPublicIpOnLaunch={'Value': True})

# Associate the route table with the subnets
route_table.associate_with_subnet(SubnetId=subnet1.id)
route_table.associate_with_subnet(SubnetId=subnet2.id)
route_table.associate_with_subnet(SubnetId=subnet3.id)

# Create a security group
print("🛡 Creating security group and setting rules...")
security_group = ec2.create_security_group(
    GroupName='HTTPSSH', 
    Description='Allow HTTP and SSH access',
    VpcId=vpc.id
)
security_group.authorize_ingress(
    IpProtocol='tcp',
    FromPort=80,
    ToPort=80,
    CidrIp='0.0.0.0/0'
)
security_group.authorize_ingress(
    IpProtocol='tcp',
    FromPort=22,
    ToPort=22,
    CidrIp='0.0.0.0/0'
)

print('✅ Security Group, VPC and all dependencies created successfully...')

# User data to install and start web server
user_data = """#!/bin/bash

# Update YUM and install HTTPD
yum update -y
yum install -y cronie cronie-anacron
yum install -y httpd mod_ssl
systemctl enable httpd
systemctl enable crond
systemctl start crond
systemctl start httpd

# Set default region
echo "region = us-east-1" >> /home/ec2-user/.aws/config

# Create mem.sh script
cat <<'EOF' > /home/ec2-user/mem.sh
#!/bin/bash
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
USEDMEMORY=$(free -m | awk 'NR==2{printf "%.2f\t", $3*100/$2 }')
LOAD_AVERAGE=$(cat /proc/loadavg | cut -d ' ' -f 1)
DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//g')  
TCP_CONN=$(netstat -an | wc -l)
TCP_CONN_PORT_80=$(netstat -an | grep 80 | wc -l)
IO_WAIT=$(iostat | awk 'NR==4 {print $5}')
aws cloudwatch put-metric-data --metric-name memory-usage --dimensions Instance=$INSTANCE_ID --namespace "Custom" --value $USEDMEMORY
aws cloudwatch put-metric-data --metric-name Tcp_connections --dimensions Instance=$INSTANCE_ID --namespace "Custom" --value $TCP_CONN
aws cloudwatch put-metric-data --metric-name TCP_connection_on_port_80 --dimensions Instance=$INSTANCE_ID --namespace "Custom" --value $TCP_CONN_PORT_80
aws cloudwatch put-metric-data --metric-name IO_WAIT --dimensions Instance=$INSTANCE_ID --namespace "Custom" --value $IO_WAIT
aws cloudwatch put-metric-data --metric-name Load_Average --dimensions Instance=$INSTANCE_ID --namespace "Custom" --value $LOAD_AVERAGE
aws cloudwatch put-metric-data --metric-name Disk_Usage --dimensions Instance=$INSTANCE_ID --namespace "Custom" --value $DISK_USAGE
EOF

# Grant execute permissions to the script
chmod +x /home/ec2-user/mem.sh

# Create a cron job to execute the script every minute
(crontab -u ec2-user -l 2>/dev/null; echo "*/1 * * * * /home/ec2-user/mem.sh") | crontab -u ec2-user -

# Install Git
yum install -y git

# Install Node.js (using Node.js 18)
curl -sL https://rpm.nodesource.com/setup_18.x | sudo bash -
sudo yum install -y nodejs

# Clone the repository
cd /var/www/html
git clone https://github.com/bakaichi/the-world-of-avatar.git
if [ $? -eq 0 ]; then
    echo "Repository cloned successfully"
    # Create .env file with necessary environment variables
    echo "Creating .env file with environment configurations"
    cat <<EOF > /var/www/html/the-world-of-avatar/.env
COOKIE_NAME=namebro
COOKIE_PASSWORD=thisissupersecretdonotsharewithanyoneatall
db=mongodb+srv://bakaichi:muffinbutton@cluster0.hcfmaar.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0
EOF
else
    echo "Failed to clone repository"
    exit 1
fi

# Install dependencies and start the application
cd the-world-of-avatar
npm install
if [ $? -eq 0 ]; then
    npm start & 
    echo "Application started successfully"
else
    echo "Failed to install dependencies"
fi

# Configure Apache for requests to Node.js app
echo "Configuring Apache for requests to Node.js application"
cat <<EOF > /etc/httpd/conf.d/node_proxy.conf
<VirtualHost *:80>
    ServerName localhost
    ProxyRequests Off
    ProxyPass / http://localhost:3000/
    ProxyPassReverse / http://localhost:3000/
    <Proxy *>
        Order deny,allow
        Allow from all
    </Proxy>
</VirtualHost>
EOF

# Restart Apache to apply configuration
systemctl restart httpd
"""

# Base64 encode the user data
encoded_user_data = base64.b64encode(user_data.encode('utf-8')).decode('utf-8')

print ("🌐 Launching an EC2 instance...")

# Launch instance
instance = ec2.create_instances(
    ImageId=ami_id,
    InstanceType='t2.nano',
    MinCount=1,
    MaxCount=1,
    NetworkInterfaces=[{
        'SubnetId': subnet1.id,
        'DeviceIndex': 0,
        'AssociatePublicIpAddress': True,
        'Groups': [security_group.id]
    }],
    UserData=encoded_user_data,
    KeyName=key_name,
    IamInstanceProfile={
        'Arn': 'arn:aws:iam::269899371745:instance-profile/LabInstanceProfile'
    },
    TagSpecifications=[{
        'ResourceType': 'instance',
        'Tags': [{'Key': 'Name', 'Value': instance_tag}]
    }]
)

# Store the instance ID
instance_id = instance[0].id
instance = instance[0] 

# Wait for the instance to start running
print('🕣 Waiting for instance to start running..')
instance.wait_until_running()

# Function to get the public IP address for the instance
def get_instance_public_ip(instance_id):
    while True:
        instance_desc = ec2_client.describe_instances(InstanceIds=[instance_id])
        public_ip = instance_desc['Reservations'][0]['Instances'][0].get('PublicIpAddress')
        if public_ip:
            return public_ip
        time.sleep(5)  # Pause before retrying if IP isn't assigned yet

public_ip = get_instance_public_ip(instance_id)
print(f'🌐 Instance public IP: {public_ip}')

# Sleep for 30 seconds to allow the instance to fully initialize
print('⏳ Waiting for 30 seconds before stopping the instance...')
time.sleep(30)

# Stop the instance
print('🛑 Stopping the instance...')
instance.stop()
instance.wait_until_stopped()

# Create AMI from the stopped instance
ami_name = f"{ami_tag}-AMI-{time.strftime('%Y%m%d-%H%M%S')}"
print('🖼 Creating AMI from the stopped instance...')
created_ami = ec2_client.create_image(InstanceId=instance_id, Name=ami_name, NoReboot=True, Description="AMI created from Master Web App")

# Wait for AMI to be available
ami_id = created_ami['ImageId']
print(f'⏳ Waiting for AMI {ami_id} to become available...')
waiter = ec2_client.get_waiter('image_available')
waiter.wait(ImageIds=[ami_id])
print(f'✅ AMI {ami_id} created and available.')

# Terminate the instance
print('🗑 Terminating the instance...')
instance.terminate()
instance.wait_until_terminated()
print('✅ Instance terminated.')

# Create Target Group
print('🔧 Creating a Target Group')
target_group = elb.create_target_group(
    Name='avatar-tg',
    Protocol='HTTP',
    Port=80,
    VpcId=vpc.id,
    TargetType='instance'
)
target_group_arn = target_group['TargetGroups'][0]['TargetGroupArn']

# Create Application Load Balancer
print('🔧 Creating a Load Balancer')
load_balancer = elb.create_load_balancer(
    Name='avatar-lb',
    Subnets=[subnet1.id, subnet2.id, subnet3.id],
    SecurityGroups=[security_group.id],
    Scheme='internet-facing',
    Tags=[{'Key': 'Name', 'Value': 'AvatarLB'}],
    IpAddressType='ipv4',
    Type='application'
)
load_balancer_arn = load_balancer['LoadBalancers'][0]['LoadBalancerArn']

# Create Listener that forwards HTTP to Target Group
listener = elb.create_listener(
    LoadBalancerArn=load_balancer_arn,
    Protocol='HTTP',
    Port=80,
    DefaultActions=[
        {
            'Type': 'forward',
            'TargetGroupArn': target_group_arn
        }
    ]
)

# Create Launch Template
print('🔧 Creating a Launch Template')
launch_template = ec2_client.create_launch_template(
    LaunchTemplateName='avatar-lt',
    VersionDescription='Initial version',
    LaunchTemplateData={
        'ImageId': ami_id,
        'InstanceType': 't2.nano',
        'KeyName': key_name,
        'SecurityGroupIds': [
            security_group.id
        ],
        'UserData': encoded_user_data,
        'IamInstanceProfile': {
            'Arn': 'arn:aws:iam::269899371745:instance-profile/LabInstanceProfile'
        },
        'Monitoring': {'Enabled': True}
    }
)

template_id = launch_template['LaunchTemplate']['LaunchTemplateId']

# Create Auto Scaling Group
print('🔧 Creating Auto Scaling Group and Alarms')
auto_scaling_group = asg.create_auto_scaling_group(
    AutoScalingGroupName='AvatarAutoScaling',
    LaunchTemplate={
        'LaunchTemplateId': template_id,
        'Version': '$Latest'
    },
    MinSize=2,
    MaxSize=3,
    DesiredCapacity=2,
    VPCZoneIdentifier=f"{subnet1.id},{subnet2.id}, {subnet3.id}",
    TargetGroupARNs=[target_group_arn],
    HealthCheckGracePeriod=180,
    HealthCheckType='ELB',
    Tags=[
        {
            'ResourceId': 'AvatarAutoScaling',
            'ResourceType': 'auto-scaling-group',
            'Key': 'Name',
            'Value': 'auto scaled instance',
            'PropagateAtLaunch': True
        }
    ]
)

# Creating Scaling Out Policy
scale_out_response = asg.put_scaling_policy(
    AutoScalingGroupName='AvatarAutoScaling',
    PolicyName='ScaleOut',
    PolicyType='StepScaling',
    AdjustmentType='ChangeInCapacity',
    StepAdjustments=[
        {'MetricIntervalLowerBound': 0, 'ScalingAdjustment': 1}
    ],
    Cooldown=120
)
scale_out_arn = scale_out_response['PolicyARN']

# Creating Scaling In Policy 
scale_in_response = asg.put_scaling_policy(
    AutoScalingGroupName='AvatarAutoScaling',
    PolicyName='ScaleIn',
    PolicyType='StepScaling',
    AdjustmentType='ChangeInCapacity',
    StepAdjustments=[
        {'MetricIntervalUpperBound': 0, 'ScalingAdjustment': -1}
    ],
    Cooldown=120
)
scale_in_arn = scale_in_response['PolicyARN']

# CloudWatch alarm for High Cpu 
cloudwatch.put_metric_alarm(
    AlarmName='HighCPUUtilization',
    MetricName='CPUUtilization',
    Namespace='AWS/EC2',
    Statistic='Average',
    Period=30,
    EvaluationPeriods=2,
    Threshold=90.0,
    ComparisonOperator='GreaterThanThreshold',
    AlarmActions=[scale_out_arn],
    Dimensions=[{'Name': 'AutoScalingGroupName', 'Value': 'AvatarAutoScaling'}]
)

# CloudWatch alarm for Low Cpu 
cloudwatch.put_metric_alarm(
    AlarmName='LowCPUUtilization',
    MetricName='CPUUtilization',
    Namespace='AWS/EC2',
    Statistic='Average',
    Period=30,
    EvaluationPeriods=2,
    Threshold=30.0,
    ComparisonOperator='LessThanThreshold',
    AlarmActions=[scale_in_arn],
    Dimensions=[{'Name': 'AutoScalingGroupName', 'Value': 'AvatarAutoScaling'}]
)


# Writing DNS to .txt file to be used to test traffic via Locust
print('🪄 Writing Load Balancer Dns to .txt file')
load_balancer_dns = load_balancer['LoadBalancers'][0]['DNSName']
with open('config.txt', 'w') as f:
    f.write(load_balancer_dns)

print('🎊 Script finished successfully.')
