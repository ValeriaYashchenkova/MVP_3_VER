pipeline {
    agent {
        kubernetes {
            inheritFrom 'python'
            defaultContainer 'python-builder'
        }
    }

    triggers {
        pollSCM('')
    }

    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
        string(
            name: 'BRANCH_NAME',
            defaultValue: 'master',
            description: 'Ветка для проверки дубликатов (например feature/duplicates-test)'
        )
    }

    environment {
        PATH = "/var/lib/jenkins/.local/bin:$PATH"
        ALLURE_RESULTS = "allure-results"
        TESTOPS_ENDPOINT = 'https://testops.moscow.alfaintra.net'
        TESTOPS_PROJECT_ID = '643'
        TESTOPS_SERVER_ID = 'testops'
    }

    stages {
        stage('Checkout SCM') {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: [[name: "${params.BRANCH_NAME}"]],
                    userRemoteConfigs: [[
                        url: 'https://git.moscow.alfaintra.net/scm/bialm_ft/bialm_ft_auto.git',
                        credentialsId: 'login_password_for_repo_bitbucket'
                    ]]
                ])
            }
        }

        stage('Create venv & Install dependencies') {
            steps {
                sh """
                    python3.7 -m venv venv || true
                    . venv/bin/activate
                    pip3.7 install --upgrade pip -i https://binary.alfabank.ru/artifactory/api/pypi/pipy-virtual/simple
                    pip3.7 install oracledb gitpython requests tomli -i https://binary.alfabank.ru/artifactory/api/pypi/pipy-virtual/simple
                """
            }
        }

        stage('Run Duplicate Checks') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'login_password_for_repo_bitbucket', usernameVariable: 'GIT_USER', passwordVariable: 'GIT_PASS')]) {
                sh """
                    . venv/bin/activate
                    rm -rf ${ALLURE_RESULTS}
                    mkdir -p ${ALLURE_RESULTS}
                    export GIT_USER=$GIT_USER
                    export GIT_PASS=$GIT_PASS
                    python run_test.py --branch ${BRANCH_NAME}
                """
            }
        }
    }

    post {
        always {
            allure includeProperties: false,
                   jdk: '',
                   results: [[path: 'allure-results']]

            script {
                try {
                    echo "Uploading results to Allure TestOps..."
                    withAllureUpload(
                        credentialsId: 'allure-token',
                        name: "Duplicate Checks #${BUILD_NUMBER} | ${BRANCH_NAME}",
                        projectId: '643',
                        results: [[path: "${WORKSPACE}/allure-results"]],
                        serverId: 'testops',
                        tags: "${BRANCH_NAME}, sql-duplicates-check"
                    ) {
                        echo "Allure TestOps upload completed"
                    }
                } catch (Exception e) {
                    echo "Failed to upload to Allure TestOps: ${e}"
                }
            }

            archiveArtifacts artifacts: 'allure-results/**', allowEmptyArchive: true
            cleanWs()
        }
    }
}
