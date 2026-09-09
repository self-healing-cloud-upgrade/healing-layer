pipeline {
    agent any

    environment {
        // We will assume these exist locally, but in a real setup 
        // they'd point to a registry (e.g. AWS ECR or Docker Hub)
        DOCKER_REGISTRY = 'localhost:5000'
        FRONTEND_IMAGE = 'niramay-frontend'
        BACKEND_IMAGE = 'niramay-backend'
        VERSION = "1.0.${env.BUILD_NUMBER}"
    }

    stages {
        stage('Checkout') {
            steps {
                // Checkout source code from the current repository
                checkout scm
            }
        }

        stage('Backend Unit Tests') {
            steps {
                dir('Niramay/backend') {
                    sh '''
                        # Setup Python virtual environment
                        python3 -m venv .venv
                        source .venv/bin/activate
                        
                        # Install dependencies
                        pip install -r requirements.txt
                        pip install pytest pytest-asyncio
                        
                        # Run Tests
                        pytest tests/ --junitxml=backend-results.xml
                    '''
                }
            }
            post {
                always {
                    junit 'Niramay/backend/backend-results.xml'
                }
            }
        }

        stage('Frontend Unit Tests') {
            steps {
                dir('Niramay/frontend') {
                    sh '''
                        # Install Node.js dependencies
                        npm install
                        
                        # Run tests with vitest
                        npm run test
                    '''
                }
            }
        }

        stage('Build Docker Images') {
            steps {
                script {
                    echo "Building Backend Image..."
                    dir('Niramay/backend') {
                        docker.build("${BACKEND_IMAGE}:${VERSION}")
                        docker.build("${BACKEND_IMAGE}:latest")
                    }

                    echo "Building Frontend Image..."
                    dir('Niramay/frontend') {
                        docker.build("${FRONTEND_IMAGE}:${VERSION}")
                        docker.build("${FRONTEND_IMAGE}:latest")
                    }
                }
            }
        }

        stage('Publish Images (Mock)') {
            steps {
                script {
                    echo "Mock Push to Registry: ${DOCKER_REGISTRY}"
                    echo "Would push ${BACKEND_IMAGE}:${VERSION}"
                    echo "Would push ${FRONTEND_IMAGE}:${VERSION}"
                    // Example command:
                    // docker.withRegistry("https://${DOCKER_REGISTRY}", 'docker-credentials-id') {
                    //     docker.image("${BACKEND_IMAGE}:${VERSION}").push()
                    //     docker.image("${FRONTEND_IMAGE}:${VERSION}").push()
                    // }
                }
            }
        }
    }

    post {
        success {
            echo "Pipeline completed successfully! Ready for deployment."
        }
        failure {
            echo "Pipeline failed. Please check the logs."
            // Here we could add Slack or Email notifications
        }
    }
}
