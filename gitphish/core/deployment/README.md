# GitPhish Deployment System

This directory contains the refactored deployment system that supports multiple deployment types.

## Architecture

### Structure
```
deployment/
├── types/                 # Deployment type implementations
│   ├── base.py           # Abstract base deployer class
│   ├── github_pages/     # GitHub Pages deployment
│   │   ├── deployer.py   # GitHub Pages implementation
│   │   └── templates/    # GitHub Pages templates

├── services/             # High-level deployment services
│   └── deployment_service.py  # Database integration service
└── factory.py           # Factory for creating deployers
```

### Deployment Types

#### GitHub Pages (`github_pages`)
- **Status**: ✅ Fully implemented
- **Purpose**: Deploy static landing pages to GitHub Pages
- **Features**: Template rendering, repository creation, Pages enablement, deployment polling



## Usage

### Basic Usage
```python
from gitphish.core.deployment.factory import create_deployer
from gitphish.config.deployment import DeploymentConfig

# GitHub Pages deployment
pages_config = DeploymentConfig(
    deployment_type='github_pages',
    github_token='your_token',
    repo_name='my-repo',
    ingest_url='https://your-server.com/ingest',
    template_preset='default'
)



# Create and use deployer
deployer = create_deployer(config)
result = deployer.deploy()
```

### Using the Factory Directly
```python
from gitphish.core.deployment.factory import DeploymentFactory
from gitphish.core.deployment.types.base import DeploymentType

# Create specific deployer type
deployer = DeploymentFactory.create_deployer(
    DeploymentType.GITHUB_PAGES, 
    config
)
```

### Database Integration
```python
from gitphish.core.deployment.services.deployment_service import DeploymentService

# For GitHub Pages
service = DeploymentService()
result = service.create_deployment(config)


```



## Adding New Deployment Types

1. **Create the deployer class**:
   ```python
   # gitphish/core/deployment/types/my_type/deployer.py
   from gitphish.core.deployment.types.base import BaseDeployer, DeploymentType
   
   class MyTypeDeployer(BaseDeployer):
       @property
       def deployment_type(self) -> DeploymentType:
           return DeploymentType.MY_TYPE
       
       def deploy(self, **kwargs) -> Dict[str, Any]:
           # Implementation here
           pass
       
       def cleanup(self) -> Dict[str, Any]:
           # Implementation here
           pass
       
       def get_deployment_status(self) -> Dict[str, Any]:
           # Implementation here
           pass
   ```

2. **Add to the enum**:
   ```python
   # gitphish/core/deployment/types/base.py
   class DeploymentType(Enum):
       GITHUB_PAGES = "github_pages"
       MY_TYPE = "my_type"  # Add here
   ```

3. **Register in factory**:
   ```python
   # gitphish/core/deployment/factory.py
   _deployers: Dict[DeploymentType, Type[BaseDeployer]] = {
       DeploymentType.GITHUB_PAGES: GitHubPagesDeployer,
       DeploymentType.MY_TYPE: MyTypeDeployer,  # Add here
   }
   ```

## Benefits

- **Extensible**: Easy to add new deployment types
- **Clean separation**: Each deployment type is self-contained
- **Type safety**: Enum-based type system prevents typos
- **Consistent interface**: All deployers implement the same BaseDeployer interface
- **Factory pattern**: Clean instantiation without tight coupling
- **Database integration**: Automatic persistence and tracking
- **Lifecycle management**: Built-in support for deployment lifecycle (create, monitor, cleanup) 