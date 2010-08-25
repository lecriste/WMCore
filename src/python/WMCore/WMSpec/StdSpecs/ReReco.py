#!/usr/bin/env python
"""
_ReReco_

Standard ReReco workflow.
"""

import subprocess

from WMCore.WMSpec.WMWorkload import newWorkload
from WMCore.WMSpec.WMStep import makeWMStep
from WMCore.WMSpec.Steps.StepFactory import getStepTypeHelper
from WMCore.Services.Requests import JSONRequests

from WMCore.Cache.ConfigCache import WMConfigCache

class ReRecoWorkloadFactory():
    """
    _ReRecoWorkloadFactory_

    Stamp out ReReco workfloads.
    """
    def getOutputModuleInfo(self, configUrl, scenarioName, scenarioFunc,
                            scenarioArgs):
        """
        _getOutputModuleInfo_

        Use the outputmodules-from-config utility to retrieve output module
        metadata.
        """
        self.encoder = JSONRequests()
        config = {"cmsPath": self.cmsPath, "scramArch": self.scramArch,
                  "frameworkVersion": self.frameworkVersion,
                  "configUrl": configUrl, "scenarioName": scenarioName,
                  "scenarioFunc": scenarioFunc, "scenarioArgs": scenarioArgs}

        outmodProcess = subprocess.Popen(["outputmodules-from-config"],
                                         stdin = subprocess.PIPE,
                                         stdout = subprocess.PIPE)
        outmodProcess.stdin.write("%s\n" % self.encoder.encode(config))
        outmodProcess.stdin.flush()

        returnCode = outmodProcess.wait()
        if returnCode != 0:
            raise Exception("Failed to get output module config.")
        
        output = outmodProcess.stdout.readline()
        return self.encoder.decode(output)
    
    def addDashboardMonitoring(self, task):
        """
        _addDashboardMonitoring_
        
        Add dashboard monitoring for the given task.
        """
        monitoring = task.data.section_("watchdog")
        monitoring.interval = 600
        monitoring.monitors = ["DashboardMonitor"]
        monitoring.section_("DashboardMonitor")
        monitoring.DashboardMonitor.softTimeOut = 300000
        monitoring.DashboardMonitor.hardTimeOut = 600000
        monitoring.DashboardMonitor.destinationHost = "cms-pamon.cern.ch"
        monitoring.DashboardMonitor.destinationPort = 8884
        return task

    def createWorkload(self):
        """
        _createWorkload_

        Create a new workload.
        """
        workload = newWorkload(self.workloadName)
        workload.setOwner(self.owner)
        workload.setStartPolicy("DatasetBlock")
        workload.setEndPolicy("SingleShot")
        workload.data.properties.acquisitionEra = self.acquisitionEra        
        return workload

    def setupProcessingTask(self, procTask, taskType, inputDataset = None, inputStep = None,
                            inputModule = None, scenarioName = None,
                            scenarioFunc = None, scenarioArgs = None, couchUrl = None,
                            couchDBName = None, configDoc = None, splitAlgo = "FileBased"):
        """
        _setupProcessingTask_

        Given an empty task add cmsRun, stagOut and logArch steps.  Configure
        the input depending on the method parameters:
          inputDataset not empty: This is a top level processing task where the
            input will be fed in by DBS.  Setup the whitelists and blacklists.
          inputDataset empty: This processing task will be fed from the output
            of another task.  The inputStep and name of the output module from
            that step (inputModule) must be specified.

        Processing config will be setup as follows:
          configDoc not empty - Use a ConfigCache config, couchUrl and
            couchDBName must not be empty.
          configDoc empty - Use a Configuration.DataProcessing config.  The
            scenarioName, scenarioFunc and scenarioArgs parameters must not be
            empty.
        """
        self.addDashboardMonitoring(procTask)
        procTaskCmssw = procTask.makeStep("cmsRun1")
        procTaskCmssw.setStepType("CMSSW")
        procTaskStageOut = procTaskCmssw.addStep("stageOut1")
        procTaskStageOut.setStepType("StageOut")
        procTaskLogArch = procTaskCmssw.addStep("logArch1")
        procTaskLogArch.setStepType("LogArchive")
        procTask.applyTemplates()
        procTask.setSplittingAlgorithm(splitAlgo, files_per_job = 1)
        procTask.addGenerator("BasicNaming")
        procTask.addGenerator("BasicCounter")
        procTask.setTaskType(taskType)
        
        if inputDataset != None:
            (primary, processed, tier) = self.inputDataset[1:].split("/")
            procTask.addInputDataset(primary = primary, processed = processed,
                                     tier = tier, dbsurl = self.dbsUrl,
                                     block_blacklist = self.blockBlackList,
                                     block_whitelist = self.blockWhiteList,
                                     run_blacklist = self.runBlackList,
                                     run_whitelist = self.runWhiteList)
            procTask.data.constraints.sites.whitelist = self.siteWhiteList
            procTask.data.constraints.sites.blacklist = self.siteBlackList
        else:
            procTask.setInputReference(inputStep, outputModule = inputModule)

        procTaskCmsswHelper = procTaskCmssw.getTypeHelper()
        procTaskCmsswHelper.setGlobalTag(self.globalTag)
        procTaskCmsswHelper.setMinMergeSize(self.minMergeSize)
        procTaskCmsswHelper.cmsswSetup(self.frameworkVersion, softwareEnvironment = "",
                                       scramArch = self.scramArch)
        if configDoc != None:
            procTaskCmsswHelper.setConfigCache(couchUrl, configDoc, couchDBName)
        else:
            procTaskCmsswHelper.setDataProcessingConfig(scenarioName, scenarioFunc,
                                                        **scenarioArgs)
        
        return procTask

    def addLogCollectTask(self, parentTask):
        """
        _addLogCollecTask_
        
        Create a LogCollect task for log archives that are produced by the
        parent task.
        """
        logCollectTask = parentTask.addTask("LogCollect")
        self.addDashboardMonitoring(logCollectTask)        
        logCollectStep = logCollectTask.makeStep("logCollect1")
        logCollectStep.setStepType("LogCollect")
        logCollectTask.applyTemplates()
        logCollectTask.setSplittingAlgorithm("EndOfRun", files_per_job = 500)
        logCollectTask.addGenerator("BasicNaming")
        logCollectTask.addGenerator("BasicCounter")
        logCollectTask.setTaskType("LogCollect")
    
        parentTaskLogArch = parentTask.getStep("logArch1")
        logCollectTask.setInputReference(parentTaskLogArch, outputModule = "logArchive")
        return

    def addOutputModule(self, parentTask, outputModuleName, dataTier,
                        filterName):
        """
        _addOutputModule_
        
        Add an output module to the geven processing task.  This will also
        create merge and cleanup tasks for the output of the output module.
        A handle to the merge task is returned to make it easy to use the merged
        output of the output module as input to another task.
        """
        if filterName != None and filterName != "":
            processedDatasetName = "%s-%s-%s" % (self.acquisitionEra, filterName,
                                                 self.processingVersion)
        else:
            processedDatasetName = "%s-%s" % (self.acquisitionEra,
                                              self.processingVersion)
        
        unmergedLFN = "%s/%s/%s" % (self.unmergedLFNBase, dataTier,
                                    processedDatasetName)
        mergedLFN = "%s/%s/%s" % (self.mergedLFNBase, dataTier,
                                  processedDatasetName)
        cmsswStep = parentTask.getStep("cmsRun1")
        cmsswStepHelper = cmsswStep.getTypeHelper()
        cmsswStepHelper.addOutputModule(outputModuleName,
                                        primaryDataset = self.inputPrimaryDataset,
                                        processedDataset = processedDatasetName,
                                        dataTier = dataTier,
                                        lfnBase = unmergedLFN,
                                        mergedLFNBase = mergedLFN)
        return self.addMergeTask(parentTask, outputModuleName, dataTier, processedDatasetName)

    def addMergeTask(self, parentTask, parentOutputModule, dataTier, processedDatasetName):
        """
        _addMergeTask_
    
        Create a merge task for files produced by the parent task.
        """
        mergeTask = parentTask.addTask("Merge%s" % parentOutputModule)
        self.addDashboardMonitoring(mergeTask)        
        mergeTaskCmssw = mergeTask.makeStep("cmsRun1")
        mergeTaskCmssw.setStepType("CMSSW")
        
        mergeTaskStageOut = mergeTaskCmssw.addStep("stageOut1")
        mergeTaskStageOut.setStepType("StageOut")
        mergeTaskLogArch = mergeTaskCmssw.addStep("logArch1")
        mergeTaskLogArch.setStepType("LogArchive")
        mergeTask.addGenerator("BasicNaming")
        mergeTask.addGenerator("BasicCounter")
        mergeTask.setTaskType("Merge")  
        mergeTask.applyTemplates()
        mergeTask.setSplittingAlgorithm("WMBSMergeBySize",
                                        max_merge_size = self.maxMergeSize,
                                        min_merge_size = self.minMergeSize,
                                        max_merge_events = self.maxMergeEvents)
    
        mergeTaskCmsswHelper = mergeTaskCmssw.getTypeHelper()
        mergeTaskCmsswHelper.cmsswSetup(self.frameworkVersion, softwareEnvironment = "",
                                        scramArch = self.scramArch)
        mergeTaskCmsswHelper.setDataProcessingConfig("cosmics", "merge")

        mergedLFN = "%s/%s/%s" % (self.mergedLFNBase, dataTier, processedDatasetName)    
        mergeTaskCmsswHelper.addOutputModule("Merged",
                                             primaryDataset = self.inputPrimaryDataset,
                                             processedDataset = processedDatasetName,
                                             dataTier = dataTier,
                                             lfnBase = mergedLFN)
    
        parentTaskCmssw = parentTask.getStep("cmsRun1")
        mergeTask.setInputReference(parentTaskCmssw, outputModule = parentOutputModule)
        self.addCleanupTask(mergeTask, parentOutputModule)
        return mergeTask

    def addCleanupTask(self, parentTask, parentOutputModuleName):
        """
        _addCleanupTask_
        
        Create a cleanup task to delete files produces by the parent task.
        """
        cleanupTask = parentTask.addTask("CleanupUnmerged%s" % parentOutputModuleName)
        self.addDashboardMonitoring(cleanupTask)        
        cleanupTask.setTaskType("Cleanup")

        parentTaskCmssw = parentTask.getStep("cmsRun1")
        cleanupTask.setInputReference(parentTaskCmssw, outputModule = parentOutputModuleName)
        cleanupTask.setSplittingAlgorithm("SiblingProcessingBased", files_per_job = 50)
       
        cleanupStep = cleanupTask.makeStep("cleanupUnmerged%s" % parentOutputModuleName)
        cleanupStep.setStepType("DeleteFiles")
        cleanupTask.applyTemplates()
        return

    def __call__(self, workloadName, arguments):
        """
        _call_

        Create a ReReco workload with the given parameters.
        """
        # Required parameters.
        self.acquisitionEra = arguments["AcquisitionEra"]
        self.owner = arguments["Requestor"]
        self.inputDataset = arguments["InputDataset"]
        self.frameworkVersion = arguments["CMSSWVersion"]
        self.scramArch = arguments["ScramArch"]
        self.processingVersion = arguments["ProcessingVersion"]
        self.skimInput = arguments["SkimInput"]
        self.globalTag = arguments["GlobalTag"]        
        self.cmsPath = arguments["CmsPath"]

        # Required parameters that can be empty.
        self.processingConfig = arguments["ProcessingConfig"]
        self.skimConfig = arguments["SkimConfig"]
        self.scenario = arguments["Scenario"]
        self.couchUrl = arguments.get("CouchUrl", "http://dmwmwriter:gutslap!@cmssrv52.fnal.gov:5984")
        self.couchDBName = arguments.get("CouchDBName", "wmagent_config_cache")        
        
        # Optional arguments.
        self.dbsUrl = arguments.get("DbsUrl", "http://cmsdbsprod.cern.ch/cms_dbs_prod_global/servlet/DBSServlet")
        self.blockBlackList = arguments.get("BlockBlackList", [])
        self.blockWhiteList = arguments.get("BlockWhiteList", [])
        self.runBlackList = arguments.get("RunBlackList", [])
        self.runWhiteList = arguments.get("RunWhiteList", [])
        self.siteBlackList = arguments.get("SiteBlackList", [])
        self.siteWhiteList = arguments.get("SiteWhiteList", [])
        self.unmergedLFNBase = arguments.get("UnmergedLFNBase", "/store/temp/WMAgent/unmerged")
        self.mergedLFNBase = arguments.get("MergedLFNBase", "/store/temp/WMAgent/merged")
        self.minMergeSize = arguments.get("MinMergeSize", 500000000)
        self.maxMergeSize = arguments.get("MaxMergeSize", 4294967296)
        self.maxMergeEvents = arguments.get("MaxMergeEvents", 100000)
        self.emulation = arguments.get("Emulation", False)

        # Derived parameters.
        #self.workloadName = workloadName or "ReReco-%s" % self.processingVersion
        #DO do: it seems it doesn't break current code - but examin that.
        self.workloadName = workloadName
        (self.inputPrimaryDataset, self.inputProcessedDataset, self.inputDataTier) = \
                                   self.inputDataset[1:].split("/")

        procConfigDoc = None
        skimConfigDoc = None
        if self.couchUrl != None and self.couchDBName != None:
            myConfigCache = WMConfigCache(dbname2 = self.couchDBName, dburl = self.couchUrl)
            if self.processingConfig != "":
                (procConfigDoc, rev) = myConfigCache.addConfig(self.processingConfig)
            if self.skimConfig != "":
                (skimConfigDoc, rev) = myConfigCache.addConfig(self.skimConfig)

        workload = self.createWorkload()
        procTask = workload.newTask("ReReco")

        self.setupProcessingTask(procTask, "Processing", self.inputDataset,
                                 scenarioName = self.scenario, scenarioFunc = "promptReco",
                                 scenarioArgs = {"globalTag": self.globalTag, "writeTiers": ["RECO", "ALCARECO"]}, 
                                 couchUrl = self.couchUrl, couchDBName = self.couchDBName,
                                 configDoc = procConfigDoc) 
        self.addLogCollectTask(procTask)

        procOutput = {}

        processingOutputModules = self.getOutputModuleInfo(self.processingConfig,
                                                           self.scenario, "promptReco",
                                                           scenarioArgs = {"globalTag": self.globalTag, "writeTiers": ["RECO", "ALCARECO"]})
        
        for (outputModuleName, datasetInfo) in processingOutputModules.iteritems():
            mergeTask = self.addOutputModule(procTask, outputModuleName, datasetInfo["dataTier"],
                                             datasetInfo["filterName"])
            procOutput[outputModuleName] = mergeTask

        if skimConfigDoc == None:
            return workload

        parentMergeTask = procOutput[self.skimInput]
        skimTask = parentMergeTask.addTask("Skims")
        parentCmsswStep = parentMergeTask.getStep("cmsRun1")
        self.setupProcessingTask(skimTask, "Skim", inputStep = parentCmsswStep, inputModule = "Merged",
                                 couchUrl = self.couchUrl, couchDBName = self.couchDBName,
                                 configDoc = skimConfigDoc, splitAlgo = "TwoFileBased")
        #addLogCollectTask(skimTask)

        skimOutputModules = self.getOutputModuleInfo(self.skimConfig,
                                                     self.scenario, "promptReco",
                                                     scenarioArgs = {})

        for (outputModuleName, datasetInfo) in skimOutputModules.iteritems():
            self.addOutputModule(skimTask, outputModuleName, datasetInfo["dataTier"],
                                 datasetInfo["filterName"])
            
        return workload

def rerecoWorkload(workloadName, arguments):
    """
    _rerecoWorkload_

    Instantiate the ReRecoWorkflowFactory and have it generate a workload for
    the given parameters.
    """
    myReRecoFactory = ReRecoWorkloadFactory()
    return myReRecoFactory(workloadName, arguments)
