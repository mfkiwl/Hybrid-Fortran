#!/usr/bin/python
# -*- coding: UTF-8 -*-

# Copyright (C) 2016 Michel Müller, Tokyo Institute of Technology

# This file is part of Hybrid Fortran.

# Hybrid Fortran is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Hybrid Fortran is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with Hybrid Fortran. If not, see <http://www.gnu.org/licenses/>.

import os, logging
from machinery.commons import updateTypeParameterProperties
from models.symbol import Symbol, DeclarationType, splitAndPurgeSpecification, uniqueIdentifier
from models.region import RegionType, ParallelRegion, CallRegion
from tools.analysis import getAnalysisForSymbol
from tools.patterns import RegExPatterns
from tools.commons import UsageError
from tools.metadata import getDomainDependantTemplatesAndEntries
from implementations.commons import *

class FortranImplementation(object):
	architecture = ["cpu", "host"]
	onDevice = False
	multipleParallelRegionsPerSubroutineAllowed = True
	assignmentToScalarsInKernelsAllowed = True
	currDependantSymbols = None
	currParallelRegionTemplateNode = None
	debugPrintIteratorDeclared = False
	currRoutineNode = None
	useOpenACCForDebugPrintStatements = True
	supportsArbitraryDataAccessesOutsideOfKernels = True
	supportsNativeMemsetsOutsideOfKernels = True
	supportsNativeModuleImportsWithinKernels = True
	usesDuplicatesAsHostRoutines = False
	allowsMixedHostAndDeviceCode = True
	useKernelPrefixesForDebugPrint = True

	def __init__(self, optionFlags, appliesTo="CPU"):
		self.patterns = RegExPatterns.Instance()
		self.currDependantSymbols = None
		self.currParallelRegionTemplateNode = None
		self.appliesTo = appliesTo
		self._currKernelNumber = 0
		if type(optionFlags) == list:
			self.optionFlags = optionFlags

	def updateSymbolDeviceState(self, symbol, symbolNamesUsedInKernel, regionType, parallelRegionPosition):
		symbol.isUsingDevicePostfix = False
		symbol.isOnDevice = False

	def adjustCalleeName(self, calleeName, calleeImplementation, callerImplementation, calleeNode, callerNode, calleeIsKernelCaller):
		if not calleeImplementation.usesDuplicatesAsHostRoutines:
			return calleeName
		if (calleeNode.getAttribute("parallelRegionPosition") in ["outside", "within"] \
			and callerNode.getAttribute("parallelRegionPosition") in [None, ""] \
		) \
		or (not callerImplementation.onDevice \
			and not calleeNode.getAttribute("parallelRegionPosition") in [None, ""] \
		):
			#calling a device function from a host routine
			return synthesizedHostRoutineName(calleeName)
		if calleeNode.getAttribute("parallelRegionPosition") == "outside" \
		or calleeIsKernelCaller \
		or (not "hfk" in calleeName and calleeNode.getAttribute("parallelRegionPosition") == "within"):
			#device routines OR routines already converted to kernel callers OR unconverted kernels
			return synthesizedDeviceRoutineName(calleeName)
		#this includes already converted kernels using CUDA Fortran implementation
		#(kernel number information contained in the name)
		return calleeName

	def adjustSpecificationForDevice(self, line, specification):
		if self.usesDuplicatesAsHostRoutines and specification == "private":
			return ""
		return line

	def generateRoutines(self, routine):
		return [routine]

	def filePreparation(self, filename):
		return '''#include "storage_order.F90"\n'''

	def warningOnUnrecognizedSubroutineCallInParallelRegion(self, callerName, calleeName):
		return ""

	def callPreparationForPassedSymbol(self, currRoutineNode, symbolInCaller):
		return ""

	def callPostForPassedSymbol(self, currRoutineNode, symbolInCaller):
		return ""

	def kernelCallConfig(self):
		return ""

	def kernelCallPreparation(self, parallelRegionTemplate, calleeNode=None):
		self.currParallelRegionTemplateNode = parallelRegionTemplate
		return ""

	def kernelCallPost(self, symbolsByName, calleeRoutineNode):
		if calleeRoutineNode.getAttribute('parallelRegionPosition') != 'within':
			return ""
		result = ""
		if 'DEBUG_PRINT' in self.optionFlags:
			result += getRuntimeDebugPrintStatements(
				calleeRoutineNode.getAttribute("name"),
				symbolsByName,
				calleeRoutineNode,
				self.currParallelRegionTemplateNode,
				useOpenACC=self.useOpenACCForDebugPrintStatements
			)
		self.currParallelRegionTemplateNode = None
		return result

	def subroutinePrefix(self, routineNode):
		return ''

	def subroutineCallInvocationPrefix(self, subroutineName, parallelRegionTemplate):
		return 'call %s' %(subroutineName)

	def getImportSpecification(self, dependantSymbolsOrModuleName, regionType, parallelRegionPosition, parallelRegionTemplates):
		return getImportStatements(dependantSymbolsOrModuleName)

	def adjustDeclarationForDevice(self, line, dependantSymbols, parentRoutine, regionType, parallelRegionPosition):
		return line

	def additionalIncludes(self):
		return ""

	def getAdditionalKernelParameters(
		self,
		currRoutine,
		callee,
		moduleNodesByName,
		symbolAnalysisByRoutineNameAndSymbolName={},
	):
		return [], [], []

	def getIterators(self, parallelRegionTemplate):
		if not appliesTo([self.appliesTo, ""], parallelRegionTemplate):
			return []
		return [domain.name for domain in getDomainsWithParallelRegionTemplate(parallelRegionTemplate)]

	def iteratorDefinitionBeforeParallelRegion(self, domains):
		return ""

	def safetyOutsideRegion(self, domains):
		return ""

	def loopPreparation(self):
		return ""

	def declarationEndPrintStatements(self):
		return ""

	def processModuleBegin(self, moduleName):
		pass

	def processModuleEnd(self):
		pass

	def parallelRegionBegin(self, dependantSymbols, parallelRegionTemplate):
		if not dependantSymbols:
			raise UsageError("parallel region without any dependant arrays")
		domains = getDomainsWithParallelRegionTemplate(parallelRegionTemplate)
		regionStr = ''
		for pos in range(len(domains)-1,-1,-1): #use inverted order (optimization of accesses for fortran storage order)
			domain = domains[pos]
			startsAt = domain.startsAt if domain.startsAt != None else "1"
			endsAt = domain.endsAt if domain.endsAt != None else domain.size
			regionStr = regionStr + 'do %s=%s,%s' %(domain.name, startsAt, endsAt)
			if pos != 0:
				regionStr = regionStr + '\n '
			pos = pos + 1
		return regionStr

	def parallelRegionEnd(self, parallelRegionTemplate, routine, skipDebugPrint=False):
		domains = getDomainsWithParallelRegionTemplate(parallelRegionTemplate)
		result = ''
		for domain in domains:
			result += 'end do\n'
		numSkippedParallelRegions = 0
		if not skipDebugPrint and 'DEBUG_PRINT' in self.optionFlags and self.allowsMixedHostAndDeviceCode:
			activeParallelRegion = None
			for region in routine.regions:
				if isinstance(region, ParallelRegion):
					if numSkippedParallelRegions == self._currKernelNumber:
						activeParallelRegion = region
						break
					else:
						numSkippedParallelRegions += 1
			if activeParallelRegion == None:
				raise Exception("cannot find active parallel region")
			activeSymbolsByName = dict(
				(symbol.name, symbol)
				for symbol in routine.symbolsByName.values()
				if symbol.name in activeParallelRegion.usedSymbolNames
			)
			result += getRuntimeDebugPrintStatements(
				synthesizedKernelName(routine.name, self._currKernelNumber) \
					if self.useKernelPrefixesForDebugPrint else routine.name,
				activeSymbolsByName,
				routine.node,
				parallelRegionTemplate,
				useOpenACC=self.useOpenACCForDebugPrintStatements
			)
			self._currKernelNumber += 1
		return result

	def declarationEnd(self, dependantSymbols, routineIsKernelCaller, currRoutineNode, currParallelRegionTemplates):
		self.currRoutineNode = currRoutineNode
		self._currKernelNumber = 0
		result = ""
		if 'DEBUG_PRINT' in self.optionFlags:
			result += "real(8) :: hf_output_temp\n"
			result += "#ifndef GPU\n"
			result += "integer(4), save :: hf_debug_print_iterator = 0\n"
			result += "#endif\n"
			self.debugPrintIteratorDeclared = True
			# if currRoutineNode.getAttribute('parallelRegionPosition') != 'inside':
			#     result += "#endif\n"
		return result + getIteratorDeclaration(currRoutineNode, currParallelRegionTemplates, [self.appliesTo, ""])

	def subroutineExitPoint(self, dependantSymbols, routineIsKernelCaller, isSubroutineEnd):
		result = ""
		if 'DEBUG_PRINT' in self.optionFlags and self.debugPrintIteratorDeclared:
			result += "#ifndef GPU\n"
			result += "hf_debug_print_iterator = hf_debug_print_iterator + 1\n"
			result += "#endif\n"
		if isSubroutineEnd:
			self.currRoutineNode = None
			self.debugPrintIteratorDeclared = False
		return result

def getWriteTraceFunc(begin_or_end):
	def writeTrace(currRoutineNode, currModuleName, symbol):
		return "write(hf_tracing_current_path, '(A,I3.3,A)') './datatrace/%s', hf_tracing_counter, '.dat'\n" %(
			tracingFilename(currModuleName, currRoutineNode, symbol, begin_or_end)
		) + "call writeToFile(hf_tracing_current_path, hf_tracing_temp_%s)\n" %(
			symbol.name
		)
	return writeTrace

class TraceGeneratingFortranImplementation(FortranImplementation):
	currRoutineNode = None
	currModuleName = None
	currentTracedSymbols = []
	earlyReturnCounter = 0

	def __init__(self, optionFlags):
		self.currentTracedSymbols = []
		self.earlyReturnCounter = 0

	def additionalIncludes(self):
		return "use helper_functions\n"

	def processModuleBegin(self, moduleName):
		self.currModuleName = moduleName

	def processModuleEnd(self):
		self.currModuleName = None

	def subroutinePrefix(self, routineNode):
		self.currRoutineNode = routineNode
		return FortranImplementation.subroutinePrefix(self, routineNode)

	def declarationEnd(self, dependantSymbols, routineIsKernelCaller, currRoutineNode, currParallelRegionTemplates):
		super_result = FortranImplementation.declarationEnd(self, dependantSymbols, routineIsKernelCaller, currRoutineNode, currParallelRegionTemplates)
		result, tracedSymbols = getTracingDeclarationStatements(currRoutineNode, dependantSymbols, self.patterns)
		self.currentTracedSymbols = tracedSymbols
		logging.info("...In subroutine %s: Symbols declared for tracing: %s" %(
				currRoutineNode.getAttribute('name'),
				[symbol.name for symbol in tracedSymbols],
			)
		)
		return result + super_result + getTracingStatements(
			self.currRoutineNode,
			self.currModuleName,
			[symbol for symbol in self.currentTracedSymbols if symbol.intent in ['in', 'inout']],
			getWriteTraceFunc('begin'),
			increment_tracing_counter=False,
			loop_name_postfix='start'
		)

	def subroutineExitPoint(self, dependantSymbols, routineIsKernelCaller, isSubroutineEnd):
		if not isSubroutineEnd:
			self.earlyReturnCounter += 1
		result = getTracingStatements(
			self.currRoutineNode,
			self.currModuleName,
			[symbol for symbol in self.currentTracedSymbols if symbol.intent in ['out', 'inout', '', None]],
			getWriteTraceFunc('end'),
			increment_tracing_counter=len(self.currentTracedSymbols) > 0,
			loop_name_postfix='end' if isSubroutineEnd else 'exit%i' %(self.earlyReturnCounter)
		)
		logging.info("...In subroutine %s: Symbols %s used for tracing" %(
				self.currRoutineNode.getAttribute('name'),
				[symbol.name for symbol in self.currentTracedSymbols]
			)
		)
		if isSubroutineEnd:
			self.earlyReturnCounter = 0
			self.currentTracedSymbols = []
		return result + FortranImplementation.subroutineExitPoint(self, dependantSymbols, routineIsKernelCaller, isSubroutineEnd)

class OpenMPFortranImplementation(FortranImplementation):
	def __init__(self, optionFlags):
		FortranImplementation.__init__(self, optionFlags)

	def parallelRegionBegin(self, dependantSymbols, parallelRegionTemplate):
		if not dependantSymbols:
			raise UsageError("parallel region without any dependant arrays")
		openMPLines = "!$OMP PARALLEL DO DEFAULT(firstprivate) %s " %(getReductionClause(parallelRegionTemplate).upper())
		openMPLines += "SHARED(%s)\n" %(', '.join([symbol.nameInScope() for symbol in dependantSymbols]))
		return openMPLines + FortranImplementation.parallelRegionBegin(self, dependantSymbols, parallelRegionTemplate)

	def parallelRegionEnd(self, parallelRegionTemplate, routine, skipDebugPrint=False):
		openMPLines = "\n!$OMP END PARALLEL DO\n"
		return FortranImplementation.parallelRegionEnd(self, parallelRegionTemplate, routine, skipDebugPrint) + openMPLines

def _checkDeclarationConformity(dependantSymbols):
	#analyse state of symbols - already declared as on device or not?
	alreadyOnDevice = "undefined"
	for symbol in dependantSymbols:
		if not symbol.domains or len(symbol.domains) == 0:
			continue
		elif symbol.isPresent and alreadyOnDevice == "undefined":
			alreadyOnDevice = "yes"
		elif not symbol.isPresent and alreadyOnDevice == "undefined":
			alreadyOnDevice = "no"
		elif (symbol.isPresent and alreadyOnDevice == "no") \
		or (not symbol.isPresent and alreadyOnDevice == "yes"):
			raise UsageError("line contains a mix of device present, non-device-present arrays. \
Symbols vs present attributes:\n%s" %(str([(symbol.name, symbol.isPresent) for symbol in dependantSymbols])) \
			)
	copyHere = "undefined"
	for symbol in dependantSymbols:
		if not symbol.domains or len(symbol.domains) == 0:
			continue
		elif symbol.isToBeTransfered and copyHere == "undefined":
			copyHere = "yes"
		elif not symbol.isToBeTransfered and copyHere == "undefined":
			copyHere = "no"
		elif (symbol.isToBeTransfered and copyHere == "no") or (not symbol.isToBeTransfered and copyHere == "yes"):
			raise UsageError("line contains a mix of transferHere / non transferHere arrays. \
Symbols vs transferHere attributes:\n%s" %(str([(symbol.name, symbol.transferHere) for symbol in dependantSymbols])) \
			)
	isOnHost = "undefined"
	for symbol in dependantSymbols:
		if not symbol.domains or len(symbol.domains) == 0:
			continue
		elif symbol.isHostSymbol and isOnHost == "undefined":
			isOnHost = "yes"
		elif not symbol.isHostSymbol and isOnHost == "undefined":
			isOnHost = "no"
		elif (symbol.isHostSymbol and symbol.isHostSymbol == "no") or (not symbol.isHostSymbol and symbol.isHostSymbol == "yes"):
			raise UsageError("line contains a mix of host / non host arrays. \
Symbols vs host attributes:\n%s" %(str([(symbol.name, symbol.isHostSymbol) for symbol in dependantSymbols])) \
			)
	if copyHere == "yes" and alreadyOnDevice == "yes":
		raise UsageError("Symbols with 'present' attribute cannot appear on the same specification line as symbols with 'transferHere' attribute.\nPresent Symbols: %s\nTransfer Symbols: %s" %(
			[symbol.name for symbols in dependantSymbols if symbol.domains and len(symbol.domains) > 0 and symbol.isPresent],
			[symbol.name for symbols in dependantSymbols if symbol.domains and len(symbol.domains) > 0 and symbol.isToBeTransfered],
		))
	if copyHere == "yes" and isOnHost == "yes":
		raise UsageError("Symbols with 'transferHere' attribute cannot appear on the same specification line as symbols with 'host' attribute.\nHost Symbols: %s\nTransfer Symbols: %s" %(
			[symbol.name for symbols in dependantSymbols if symbol.domains and len(symbol.domains) > 0 and symbol.isHostSymbol],
			[symbol.name for symbols in dependantSymbols if symbol.domains and len(symbol.domains) > 0 and symbol.isToBeTransfered],
		))
	if alreadyOnDevice == "yes" and isOnHost == "yes":
		raise UsageError("Symbols with 'present' attribute cannot appear on the same specification line as symbols with 'host' attribute.\nHost Symbols: %s\nPresent Symbols: %s" %(
			[symbol.name for symbols in dependantSymbols if symbol.domains and len(symbol.domains) > 0 and symbol.isHostSymbol],
			[symbol.name for symbols in dependantSymbols if symbol.domains and len(symbol.domains) > 0 and symbol.isPresent],
		))
	isTypeParameter = "undefined"
	for symbol in dependantSymbols:
		if symbol.isTypeParameter and isTypeParameter == "undefined":
			isTypeParameter = "yes"
		elif not symbol.isTypeParameter and isTypeParameter == "undefined":
			isTypeParameter = "no"
		elif (symbol.isTypeParameter and isTypeParameter == "no") or (not symbol.isTypeParameter and isTypeParameter == "yes"):
			raise UsageError("line contains a mix of type parameter / non type parameter symbols: %s; is type parameter: %s" %(
				dependantSymbols, [symbol.isTypeParameter for symbol in dependantSymbols]
			))
	return alreadyOnDevice, copyHere, isOnHost

class DeviceDataFortranImplementation(FortranImplementation):
	def updateSymbolDeviceState(self, symbol, symbolNamesUsedInKernel, regionType, parallelRegionPosition, postTransfer=False):
		logging.debug("device state of symbol %s BEFORE update:\nisOnDevice: %s; isUsingDevicePostfix: %s" %(
			symbol.name,
			symbol.isOnDevice,
			symbol.isUsingDevicePostfix
		))

		#packed symbols -> leave them alone
		if symbol.isCompacted:
			return

		#symbol explicitely marked for host, which is allowed in this implementation - leave it alone
		if self.allowsMixedHostAndDeviceCode and symbol.isHostSymbol:
			return

		if parallelRegionPosition in ["within", "outside"]:
			symbol.isPresent = True
			symbol.isToBeTransfered = False

		#passed in scalars in kernels and inside kernels
		if parallelRegionPosition in ["within", "outside"] \
		and len(symbol.domains) == 0 \
		and symbol.intent not in ["out", "inout", "local"]:
			symbol.isOnDevice = True

		#arrays..
		elif len(symbol.domains) > 0:

			#.. marked as host symbol
			if symbol.isHostSymbol and regionType == RegionType.MODULE_DECLARATION:
				#this might look confusing. We want to declare a device version but note that the data is not yet residing there
				symbol.isUsingDevicePostfix = True
				symbol.isOnDevice = False

			elif symbol.isHostSymbol \
			and regionType == RegionType.KERNEL_CALLER_DECLARATION \
			and (symbolNamesUsedInKernel == None or symbol.name in symbolNamesUsedInKernel):
				#for kernel calls, assume that the programmer or previous automation has handled the transfer through directives
				symbol.isUsingDevicePostfix = True
				symbol.isOnDevice = True

			elif symbol.isHostSymbol:
				symbol.isUsingDevicePostfix = False
				symbol.isOnDevice = False

			#.. imports / module scope
			elif symbol.declarationType == DeclarationType.MODULE_ARRAY \
			and parallelRegionPosition not in ["", None]:
				symbol.isUsingDevicePostfix = True
				symbol.isOnDevice = True

			#.. marked as present or locals in kernel callers
			elif symbol.isPresent \
			or (symbol.intent in [None, "", "local"] and regionType == RegionType.KERNEL_CALLER_DECLARATION):
				symbol.isUsingDevicePostfix = False
				symbol.isOnDevice = True

			#.. marked to be transferred or in a kernel caller
			elif symbol.isToBeTransfered \
			or regionType == RegionType.KERNEL_CALLER_DECLARATION:
				symbol.isUsingDevicePostfix = postTransfer
				symbol.isOnDevice = postTransfer

		logging.debug("device state of symbol %s AFTER update:\nisOnDevice: %s; isUsingDevicePostfix: %s" %(
			symbol.name,
			symbol.isOnDevice,
			symbol.isUsingDevicePostfix
		))

	def adjustDeclarationForDevice(self, line, dependantSymbols, parentRoutine, regionType, parallelRegionPosition):
		def declarationStatements(dependantSymbols, declarationDirectives, deviceType):
			return "\n".join(
				"%s, %s :: %s" %(declarationDirectives, deviceType, symbol.domainRepresentation(parentRoutine))
				for symbol in dependantSymbols
			)

		if not dependantSymbols or len(dependantSymbols) == 0:
			raise Exception("no symbols to adjust")
		for symbol in dependantSymbols:
			if regionType in [RegionType.MODULE_DECLARATION, RegionType.KERNEL_CALLER_DECLARATION] \
			or symbol.isToBeTransfered:
				self.updateSymbolDeviceState(
					symbol,
					parentRoutine.usedSymbolNamesInKernels if parentRoutine else None,
					regionType, parallelRegionPosition,
					postTransfer=True
				)
		alreadyOnDevice = None
		copyHere = None
		try:
			alreadyOnDevice, copyHere, _ = _checkDeclarationConformity(dependantSymbols)
		except UsageError as e:
			raise UsageError("In %s: %s; symbols: %s" %(line.strip(), str(e), dependantSymbols))
		adjustedLine = line.rstrip()

		#$$$ generalize this using using symbol.getSanitizedDeclarationPrefix with a new 'intent' parameter
		purgeList=['intent', 'dimension', 'save', 'optional']
		if len(dependantSymbols[0].domains) > 0:
			purgeList.append('parameter') #data intrinsics are not allowed for device arrays.
		purgedDeclarationDirectives, declarationDirectives, symbolDeclarationStr = splitAndPurgeSpecification(line, purgeList)
		deviceType = "device"
		declarationType = dependantSymbols[0].declarationType

		if dependantSymbols[0].isCompacted:
			return purgedDeclarationDirectives + " :: " + symbolDeclarationStr + "\n"

		#analyse the intent of the symbols. Since one line can only have one intent declaration, we can simply assume the intent of the
		#first symbol
		#note: intent == None or "" -> is local array
		intent = dependantSymbols[0].intent

		#scalars in kernels ...
		if parallelRegionPosition == "within" \
		and len(dependantSymbols[0].domains) == 0:
			#... not meant for output (if we can't do reductions just induce a potential compiler error at this point)
			if ( \
				intent not in ["out", "inout"] or not self.assignmentToScalarsInKernelsAllowed \
			) \
			and not "character" in purgedDeclarationDirectives:
				adjustedLine = purgedDeclarationDirectives + ", value :: " + symbolDeclarationStr

			#... meant for output
			else:
				adjustedLine = purgedDeclarationDirectives + ", intent(%s) :: " %(intent) + symbolDeclarationStr

		#arrays...
		elif len(dependantSymbols[0].domains) > 0:
			#present
			if alreadyOnDevice == "yes" or (intent in [None, "", "local"] and regionType == RegionType.KERNEL_CALLER_DECLARATION):
				adjustedLine = declarationStatements(
					dependantSymbols,
					purgedDeclarationDirectives if parallelRegionPosition in ["within", "outside"] else declarationDirectives,
					deviceType
				)

			#to be transferred
			elif copyHere == "yes" or regionType in [RegionType.KERNEL_CALLER_DECLARATION, RegionType.MODULE_DECLARATION]:
				adjustedLine += "\n" + declarationStatements(dependantSymbols, purgedDeclarationDirectives, deviceType)

		return adjustedLine + "\n"

	def declarationEnd(self, dependantSymbols, routineIsKernelCaller, currRoutineNode, currParallelRegionTemplates):
		self._currKernelNumber = 0
		deviceInitStatements = ""
		for symbol in dependantSymbols:
			if not symbol.domains or len(symbol.domains) == 0:
				continue
			if not symbol.isOnDevice:
				continue
			if symbol.isPresent:
				continue
			dimSizes = [dimSize for _, dimSize in symbol.domains]
			if (routineIsKernelCaller or symbol.isToBeTransfered) and symbol.hasUndecidedDomainSizes:
				if not ":" in dimSizes:
					if not symbol.isToBeTransfered:
						logging.info("Generating implicit device data allocation for %s in %s" %(
							symbol.name,
							currRoutineNode.getAttribute("name")
						))
					deviceInitStatements += arrayCheckConditional(symbol) + "\n"
					try:
						deviceInitStatements += "allocate(%s)\n" %(symbol.allocationRepresentation())
					except Exception as e:
						raise Exception("Cannot allocate symbol %s (domains %s) here. Routine is kernel caller: %s, symbol to be transferred: %s" %(
							symbol.name,
							symbol.domains,
							routineIsKernelCaller,
							symbol.isToBeTransfered
						))
					deviceInitStatements += "end if\n"
			if (symbol.intent in ["in", "inout"] or symbol.declarationType == DeclarationType.MODULE_ARRAY) \
			and (routineIsKernelCaller or symbol.isToBeTransfered):
				if not ":" in dimSizes:
					deviceInitStatements += arrayCheckConditional(symbol) + "\n"
					symbol.isUsingDevicePostfix = False
					originalStr = symbol.selectAllRepresentation()
					symbol.isUsingDevicePostfix = True
					deviceStr = symbol.selectAllRepresentation()
					deviceInitStatements += deviceStr + " = " + originalStr + "\n"
					deviceInitStatements += "end if\n"
			elif (routineIsKernelCaller or symbol.isToBeTransfered):
				deviceInitStatements += symbol.selectAllRepresentation() + " = 0\n"
		return deviceInitStatements

	def subroutineExitPoint(self, dependantSymbols, routineIsKernelCaller, isSubroutineEnd):
		deviceInitStatements = ""
		for symbol in dependantSymbols:
			if not symbol.domains or len(symbol.domains) == 0:
				continue
			if not symbol.isOnDevice:
				continue
			if symbol.isPresent:
				continue
			dimSizes = [dimSize for _, dimSize in symbol.domains]
			if (symbol.intent in ["out", "inout"] or symbol.declarationType == DeclarationType.MODULE_ARRAY) \
			and (routineIsKernelCaller or symbol.isToBeTransfered):
				if not ":" in dimSizes:
					deviceInitStatements += arrayCheckConditional(symbol) + "\n"
					symbol.isUsingDevicePostfix = False
					originalStr = symbol.selectAllRepresentation()
					symbol.isUsingDevicePostfix = True
					deviceStr = symbol.selectAllRepresentation()
					deviceInitStatements += originalStr + " = " + deviceStr + "\n"
					deviceInitStatements += "end if\n"
			if (routineIsKernelCaller or symbol.isToBeTransfered) and symbol.hasUndecidedDomainSizes:
				if not ":" in dimSizes:
					deviceInitStatements += arrayCheckConditional(symbol) + "\n"
					deviceInitStatements += "deallocate(%s)\n" %(symbol.nameInScope())
					deviceInitStatements += "end if\n"
		return deviceInitStatements + FortranImplementation.subroutineExitPoint(self, dependantSymbols, routineIsKernelCaller, isSubroutineEnd)

class PGIOpenACCFortranImplementation(DeviceDataFortranImplementation):
	architecture = ["openacc", "gpu", "nvd", "nvidia"]
	onDevice = True
	createDeclaration = "create"

	def __init__(self, optionFlags):
		super(PGIOpenACCFortranImplementation, self).__init__(optionFlags)
		self.currRoutineNode = None
		self.createDeclaration = "create"
		self.currParallelRegionTemplates = None

	def filePreparation(self, filename):
		additionalStatements = '''
attributes(global) subroutine HF_DUMMYKERNEL_%s()
use cudafor
!This ugly hack is used because otherwise as of PGI 14.7, OpenACC kernels could not be used in code that is compiled with CUDA flags.
end subroutine
		''' %(os.path.basename(filename).split('.')[0])
		return super(PGIOpenACCFortranImplementation, self).filePreparation(filename) + additionalStatements

	def additionalIncludes(self):
		return super(PGIOpenACCFortranImplementation, self).additionalIncludes() + "use openacc\nuse cudafor\n"

	def callPreparationForPassedSymbol(self, currRoutineNode, symbolInCaller):
		if symbolInCaller.isHostSymbol:
			return ""
		#$$$ may need to be replaced with CUDA Fortran style manual update
		# if not currRoutineNode:
		# 	return ""
		# if currRoutineNode.getAttribute("parallelRegionPosition") != 'inside':
		# 	return ""
		# if symbolInCaller.declarationType != DeclarationType.LOCAL_ARRAY:
		# 	return ""
		# return "!$acc update device(%s)\n" %(symbolInCaller.name)
		return ""

	def callPostForPassedSymbol(self, currRoutineNode, symbolInCaller):
		if symbolInCaller.isHostSymbol:
			return ""
		#$$$ may need to be replaced with CUDA Fortran style manual update
		# if not currRoutineNode:
		# 	return ""
		# if currRoutineNode.getAttribute("parallelRegionPosition") != 'inside':
		# 	return ""
		# if symbolInCaller.declarationType != DeclarationType.LOCAL_ARRAY:
		# 	return ""
		# return "!$acc update host(%s)\n" %(symbolInCaller.name)
		return ""

	def declarationEnd(self, dependantSymbols, routineIsKernelCaller, currRoutineNode, currParallelRegionTemplates):
		self.currRoutineNode = currRoutineNode
		self.currParallelRegionTemplates = currParallelRegionTemplates
		result = ""
		if 'DEBUG_PRINT' in self.optionFlags:
			result += "real(8) :: hf_output_temp\n"
		result += getIteratorDeclaration(currRoutineNode, currParallelRegionTemplates, ["GPU"])
		result += super(PGIOpenACCFortranImplementation, self).declarationEnd(
			dependantSymbols,
			routineIsKernelCaller,
			currRoutineNode,
			currParallelRegionTemplates
		)
		result += self.declarationEndPrintStatements()
		return result

	def getIterators(self, parallelRegionTemplate):
		if not appliesTo(["GPU"], parallelRegionTemplate):
			return []
		return [domain.name for domain in getDomainsWithParallelRegionTemplate(parallelRegionTemplate)]

	def loopPreparation(self):
		return "!$acc loop seq"

	def parallelRegionBegin(self, dependantSymbols, parallelRegionTemplate):
		if not dependantSymbols:
			raise UsageError("parallel region without any dependant arrays")
		regionStr = ""
		#$$$ may need to be replaced with CUDA Fortran style manual update
		# for symbol in self.currDependantSymbols:
		# 	if symbol.declarationType == DeclarationType.LOCAL_ARRAY:
		# 		regionStr += "!$acc update device(%s)\n" %(symbol.name)
		vectorSizePPNames = getVectorSizePPNames(parallelRegionTemplate)
		regionStr += "!$acc kernels "
		for symbol in dependantSymbols:
			if len(symbol.domains) == 0:
				continue
			if symbol.isOnDevice:
				regionStr += "deviceptr(%s) " %(symbol.name)
		regionStr += "\n"
		domains = getDomainsWithParallelRegionTemplate(parallelRegionTemplate)
		if len(domains) > 3 or len(domains) < 1:
			raise UsageError("Invalid number of parallel domains in parallel region definition.")
		for pos in range(len(domains)-1,-1,-1): #use inverted order (optimization of accesses for fortran storage order)
			regionStr += "!$acc loop independent vector(%s) " %(vectorSizePPNames[pos])
			# reduction clause is broken in 15.3. better to let the compiler figure it out.
			# if pos == len(domains)-1:
			#     regionStr += getReductionClause(parallelRegionTemplate)
			regionStr += "\n"
			domain = domains[pos]
			startsAt = domain.startsAt if domain.startsAt != None else "1"
			endsAt = domain.endsAt if domain.endsAt != None else domain.size
			regionStr += 'do %s=%s,%s' %(domain.name, startsAt, endsAt)
			if pos != 0:
				regionStr += '\n '
		return regionStr

	def parallelRegionEnd(self, parallelRegionTemplate, routine, skipDebugPrint=False):
		additionalStatements = "\n!$acc end kernels\n"
		#$$$ may need to be replaced with CUDA Fortran style manual update
		# for symbol in self.currDependantSymbols:
		# 	if symbol.declarationType == DeclarationType.LOCAL_ARRAY:
		# 		additionalStatements += "!$acc update host(%s)\n" %(symbol.name)
		result = super(PGIOpenACCFortranImplementation, self).parallelRegionEnd(
			parallelRegionTemplate,
			routine,
			skipDebugPrint=True
		) + additionalStatements
		if not skipDebugPrint and 'DEBUG_PRINT' in self.optionFlags and self.allowsMixedHostAndDeviceCode:
			activeSymbolsByName = dict(
				(symbol.name, symbol)
				for symbol in routine.symbolsByName.values()
				if symbol.name in routine.usedSymbolNamesInKernels
			)
			result += getRuntimeDebugPrintStatements(
				synthesizedKernelName(routine.name, self._currKernelNumber),
				activeSymbolsByName,
				routine.node,
				parallelRegionTemplate,
				useOpenACC=self.useOpenACCForDebugPrintStatements
			)
			self._currKernelNumber += 1
		return result

	#MMU: we first need a branch analysis on the subroutine to do this
	# def subroutinePostfix(self, routineNode):
	#     parallelRegionPosition = routineNode.getAttribute("parallelRegionPosition")
	#     if parallelRegionPosition == "outside":
	#         return "!$acc routine seq\n"
	#     return ""

	def subroutineExitPoint(self, dependantSymbols, routineIsKernelCaller, isSubroutineEnd):
		if isSubroutineEnd:
			self.currRoutineNode = None
			self.currRoutineHasDataDeclarations = False
			self.currParallelRegionTemplates = None
		return super(PGIOpenACCFortranImplementation, self).subroutineExitPoint(
			dependantSymbols,
			routineIsKernelCaller,
			isSubroutineEnd
		)

class DebugPGIOpenACCFortranImplementation(PGIOpenACCFortranImplementation):
	def kernelCallPreparation(self, parallelRegionTemplate, calleeNode=None):
		result = PGIOpenACCFortranImplementation.kernelCallPreparation(self, parallelRegionTemplate, calleeNode)
		if calleeNode != None:
			routineName = calleeNode.getAttribute('name')
			result += "write(0,*) 'calling kernel %s'\n" %(routineName)
		return result

	def declarationEndPrintStatements(self):
		if self.currRoutineNode.getAttribute('parallelRegionPosition') == 'outside':
			return ""
		result = PGIOpenACCFortranImplementation.declarationEndPrintStatements(self)
		routineName = self.currRoutineNode.getAttribute('name')
		result += "write(0,*) 'entering subroutine %s'\n" %(routineName)
		return result

class TraceCheckingOpenACCFortranImplementation(DebugPGIOpenACCFortranImplementation):
	currRoutineNode = None
	currModuleName = None
	currentTracedSymbols = []
	earlyReturnCounter = 0

	def __init__(self, optionFlags):
		DebugPGIOpenACCFortranImplementation.__init__(self, optionFlags)
		self.currentTracedSymbols = []

	def additionalIncludes(self):
		return DebugPGIOpenACCFortranImplementation.additionalIncludes(self) + "use helper_functions\nuse cudafor\n"

	def processModuleBegin(self, moduleName):
		self.currModuleName = moduleName

	def processModuleEnd(self):
		self.currModuleName = None

	def subroutinePrefix(self, routineNode):
		self.currRoutineNode = routineNode
		return DebugPGIOpenACCFortranImplementation.subroutinePrefix(self, routineNode)

	def declarationEnd(self, dependantSymbols, routineIsKernelCaller, currRoutineNode, currParallelRegionTemplates):
		openACCDeclarations = DebugPGIOpenACCFortranImplementation.declarationEnd(self, dependantSymbols, routineIsKernelCaller, currRoutineNode, currParallelRegionTemplates)
		result = "integer(4) :: hf_tracing_imt, hf_tracing_ierr\n"
		result += "real(8) :: hf_tracing_error\n"
		result += "real(8) :: hf_mean_ref\n"
		result += "real(8) :: hf_mean_gpu\n"
		result += "integer(8) :: hf_num_of_elements\n"
		result += "logical :: hf_tracing_error_found\n"
		tracing_declarations, tracedSymbols = getTracingDeclarationStatements(
			currRoutineNode,
			dependantSymbols,
			self.patterns,
			useReorderingByAdditionalSymbolPrefixes={'hf_tracing_temp_':False, 'hf_tracing_comparison_':False}
		)
		result += tracing_declarations
		result += openACCDeclarations
		self.currentTracedSymbols = tracedSymbols
		result += "hf_tracing_error_found = .false.\n"
		result += "hf_tracing_error = 0.0d0\n"
		result += getTracingStatements(
			self.currRoutineNode,
			self.currModuleName,
			[symbol for symbol in self.currentTracedSymbols if symbol.intent in ['in', 'inout']],
			getCompareToTraceFunc(abortSubroutineOnError=False, loop_name_postfix='start', begin_or_end='begin'),
			increment_tracing_counter=False,
			loop_name_postfix='start'
		)
		# if len(self.currentTracedSymbols) > 0:
		#     result += "if (hf_tracing_error_found) then\n"
		#     result += "stop 2\n"
		#     result += "end if\n"

		return getIteratorDeclaration(currRoutineNode, currParallelRegionTemplates, ["GPU"]) + result

	def subroutineExitPoint(self, dependantSymbols, routineIsKernelCaller, isSubroutineEnd):
		if not isSubroutineEnd:
			self.earlyReturnCounter += 1
		result = getTracingStatements(
			self.currRoutineNode,
			self.currModuleName,
			[symbol for symbol in self.currentTracedSymbols if symbol.intent in ['out', 'inout', '', None]],
			getCompareToTraceFunc(
				abortSubroutineOnError=False,
				loop_name_postfix='end' if isSubroutineEnd else 'exit%i' %(self.earlyReturnCounter),
				begin_or_end='end'
			),
			increment_tracing_counter=len(self.currentTracedSymbols) > 0,
			loop_name_postfix='end' if isSubroutineEnd else 'exit%i' %(self.earlyReturnCounter)
		)
		# if len(self.currentTracedSymbols) > 0:
		#     result += "if (hf_tracing_error_found) then\n"
		#     result += "stop 2\n"
		#     result += "end if\n"
		result += DebugPGIOpenACCFortranImplementation.subroutineExitPoint(self, dependantSymbols, routineIsKernelCaller, isSubroutineEnd)
		if isSubroutineEnd:
			self.earlyReturnCounter = 0
			self.currRoutineNode = None
			self.currentTracedSymbols = []
		return result

class CUDAFortranImplementation(DeviceDataFortranImplementation):
	architecture = ["cuda", "gpu", "nvd", "nvidia"]
	onDevice = True
	multipleParallelRegionsPerSubroutineAllowed = False
	assignmentToScalarsInKernelsAllowed = False
	useOpenACCForDebugPrintStatements = False
	supportsArbitraryDataAccessesOutsideOfKernels = False
	supportsNativeMemsetsOutsideOfKernels = True
	supportsNativeModuleImportsWithinKernels = False
	usesDuplicatesAsHostRoutines = True
	allowsMixedHostAndDeviceCode = False

	def __init__(self, optionFlags):
		self.currRoutineNode = None
		super(CUDAFortranImplementation, self).__init__(optionFlags)

	def generateRoutines(self, routine):
		def generateHostRoutine(routine):
			hostRoutine = routine.clone(synthesizedHostRoutineName(routine.name))
			hostRoutine.implementation = FortranImplementation(self.optionFlags, appliesTo="GPU")
			hostRoutine.implementation.useKernelPrefixesForDebugPrint = False
			return hostRoutine

		routines = [routine]
		if routine.node.getAttribute("parallelRegionPosition") == "outside":
			hostRoutine = generateHostRoutine(routine)
			routines.append(hostRoutine)
			routines[0].name = synthesizedDeviceRoutineName(routines[0].name)

		if routine.node.getAttribute("parallelRegionPosition") != "within":
			return routines

		routines.append(generateHostRoutine(routine))
		parallelRegions = [region for region in routine.regions if isinstance(region, ParallelRegion)]
		kernelRoutinesByName = {}
		for kernelNumber, parallelRegion in enumerate(parallelRegions):
			kernelName = synthesizedKernelName(routine.name, kernelNumber)
			kernelRoutine = routine.createCloneWithMetadata(kernelName)
			kernelRoutine.resetRegions(routine.regions[0].clone())
			kernelRoutine.addRegion(parallelRegion)
			kernelRoutine.node.setAttribute("parallelRegionPosition", "within")
			kernelRoutine.node.setAttribute("name", kernelName)
			kernelRoutine.parallelRegionTemplates = [parallelRegion.template]
			kernelRoutinesByName[kernelName] = kernelRoutine
			routines.append(kernelRoutine)

		kernelWrapperRegions = []
		parallelRegionIndex = 0
		for region in routine.regions:
			if not isinstance(region, ParallelRegion):
				kernelWrapperRegions.append(region)
				continue
			kernelName = synthesizedKernelName(routine.name, parallelRegionIndex)
			kernelRoutine = kernelRoutinesByName[kernelName]
			callRegion = CallRegion(routine)
			routine.loadCall(kernelRoutine, overrideRegion=callRegion)
			kernelWrapperRegions.append(callRegion)
			parallelRegionIndex += 1

		routines[0].name = synthesizedDeviceRoutineName(routines[0].name)
		routine.node.setAttribute("parallelRegionPosition", "inside")
		routine.node.setAttribute("isKernelCaller", "yes")
		routine.parallelRegionTemplates = []
		routine.regions = kernelWrapperRegions
		return routines

	def warningOnUnrecognizedSubroutineCallInParallelRegion(self, callerName, calleeName):
		return "subroutine %s called inside %s's parallel region, but it is not defined in a h90 file.\n" %(
			calleeName, callerName
		)

	def kernelCallConfig(self):
		return "<<< cugrid, cublock >>>"

	def kernelCallPreparation(self, parallelRegionTemplate, calleeNode=None):
		result = super(CUDAFortranImplementation, self).kernelCallPreparation(parallelRegionTemplate, calleeNode)
		if not appliesTo(["GPU"], parallelRegionTemplate):
			return ""
		gridPreparationStr = ""
		if calleeNode != None and "DO_NOT_TOUCH_GPU_CACHE_SETTINGS" not in self.optionFlags:
			gridPreparationStr += "cuerror = cudaFuncSetCacheConfig(%s, cudaFuncCachePreferL1)\n" %(calleeNode.getAttribute('name'))
			gridPreparationStr += "cuerror = cudaGetLastError()\n"
			gridPreparationStr += "if(cuerror .NE. cudaSuccess) then\n \
	\twrite(0, *) 'CUDA error when setting cache configuration for kernel %s:', cudaGetErrorString(cuerror)\n \
	stop 1\n\
end if\n" %(calleeNode.getAttribute('name'))
		blockSizePPNames = getVectorSizePPNames(parallelRegionTemplate)
		gridSizeVarNames = ["cugridSizeX", "cugridSizeY", "cugridSizeZ"]
		domains = getDomainsWithParallelRegionTemplate(parallelRegionTemplate)
		if len(domains) > 3 or len(domains) < 1:
			raise UsageError("Invalid number of parallel domains in parallel region definition.")
		blockStr = "cublock = dim3("
		gridStr = "cugrid = dim3("
		for i in range(3):
			if i != 0:
				gridPreparationStr += "\n"
				gridStr += ", "
				blockStr += ", "
			if i < len(domains):
				domainComponents = domains[i].size.split(":")
				domainSizeSpecification = None
				if len(domainComponents) == 1:
					domainSizeSpecification = domainComponents[0]
				elif len(domainComponents) == 2:
					domainSizeSpecification = "%s - %s + 1" %(domainComponents[1], domainComponents[0])
				gridPreparationStr += "%s = ceiling(real(%s) / real(%s))" %(
					gridSizeVarNames[i],
					domainSizeSpecification,
					blockSizePPNames[i]
				)
				blockStr += "%s" %(blockSizePPNames[i])
			else:
				gridPreparationStr +=  "%s = 1" %(gridSizeVarNames[i])
				blockStr += "1"
			gridStr += "%s" %(gridSizeVarNames[i])
		result += gridPreparationStr + "\n" + gridStr + ")\n" + blockStr + ")\n"
		return result

	def kernelCallPost(self, symbolsByName, calleeRoutineNode):
		result = super(CUDAFortranImplementation, self).kernelCallPost(symbolsByName, calleeRoutineNode)
		if calleeRoutineNode.getAttribute('parallelRegionPosition') != 'within':
			return result
		result += getCUDAErrorHandling(calleeRoutineNode)
		return result

	def getImportSpecification(self, dependantSymbolsOrModuleName, regionType, parallelRegionPosition, parallelRegionTemplates):
		dependantSymbols = []
		if isinstance(dependantSymbolsOrModuleName, list):
			dependantSymbols = dependantSymbolsOrModuleName

		for symbol in dependantSymbols:
			if symbol.isToBeTransfered or regionType in [RegionType.MODULE_DECLARATION, RegionType.KERNEL_CALLER_DECLARATION]:
				self.updateSymbolDeviceState(symbol, None, RegionType.OTHER, parallelRegionPosition, postTransfer=True)

		if len(dependantSymbols) > 0:
			if dependantSymbols[0].isTypeParameter:
				return getImportStatements(dependantSymbols)
			if parallelRegionPosition == "within":
				return ""
			if parallelRegionPosition == "outside":
				raise UsageError(
					"Importing symbols %s to device routine %s (routine called within kernel) is not supported. Please pass as argument instead." %(
						dependantSymbols,
						dependantSymbols[0].nameOfScope
					)
				)
			if len(dependantSymbols) == 0:
				return ""
			if dependantSymbols[0].isHostSymbol:
				return getImportStatements(dependantSymbols, forceHostVersion=True)
			if dependantSymbols[0].isPresent \
			or dependantSymbols[0].isToBeTransfered \
			or regionType in [
				RegionType.KERNEL_CALLER_DECLARATION,
				RegionType.MODULE_DECLARATION
			]:
				return getImportStatements(dependantSymbols) \
					+ getImportStatements(dependantSymbols, forceHostVersion=True)
		return getImportStatements(dependantSymbolsOrModuleName)

	def getAdditionalKernelParameters(
		self,
		currRoutine,
		callee,
		moduleNodesByName,
		symbolAnalysisByRoutineNameAndSymbolName={},
	):
		def indexSymbolsByNameInScope(symbols):
			return dict(
				(symbol.nameInScope(useDeviceVersionIfAvailable=False), symbol)
				for symbol in symbols
			)

		def mergeSymbols(symbols, index):
			for symbol in symbols:
				name = symbol.nameInScope(useDeviceVersionIfAvailable=False)
				if name in index:
					symbol.merge(index[name])
					del index[name]

		def getAdditionalImportsAndDeclarationsForParentScope(parentNode, argumentSymbolNames):
			additionalImports = []
			additionalDeclarations = []
			additionalDummies = []
			dependantTemplatesAndEntries = getDomainDependantTemplatesAndEntries(parentNode.ownerDocument, parentNode)
			for template, entry in dependantTemplatesAndEntries:
				dependantName = entry.firstChild.nodeValue
				if dependantName in argumentSymbolNames:
					continue #in case user is working with slices and passing them to different symbols inside the kernel, he has to manage that stuff manually
				symbol = currRoutine.symbolsByName.get(uniqueIdentifier(dependantName, currRoutine.name))
				if not symbol:
					symbol = currRoutine.symbolsByName.get(uniqueIdentifier(dependantName, currRoutine.parentModule.name))
				if not symbol:
					symbol = currRoutine.symbolsByName.get(dependantName)
				if not symbol:
					logging.debug("while analyzing additional kernel parameters: symbol %s was not available yet for parent %s, so it was loaded freshly;\nCurrent symbols:%s\n" %(
						dependantName,
						parentNode.getAttribute('name'),
						currRoutine.symbolsByName.keys()
					))
					symbol = Symbol(
						dependantName,
						template,
						symbolEntry=entry,
						scopeNode=parentNode,
						analysis=getAnalysisForSymbol(symbolAnalysisByRoutineNameAndSymbolName, parentNode.getAttribute('name'), dependantName),
						parallelRegionTemplates=callee.parallelRegionTemplates
					)
					symbol.loadRoutineNodeAttributes(parentNode, callee.parallelRegionTemplates)
					updateTypeParameterProperties(symbol, currRoutine.symbolsByName.values())
				if symbol.isTypeParameter:
					continue
				if symbol.isDummySymbolForRoutine(routineName=parentNode.getAttribute('name')):
					continue #already passed manually
				if symbol.isHostSymbol \
				and not symbol.name in currRoutine.usedSymbolNamesInKernels \
				and not symbol.name in callee.usedSymbolNamesInKernels:
					continue
				isModuleSymbol = symbol.declarationType in [
					DeclarationType.LOCAL_MODULE_SCALAR,
					DeclarationType.MODULE_ARRAY,
					DeclarationType.MODULE_ARRAY_PASSED_IN_AS_ARGUMENT
				]
				if isModuleSymbol and currRoutine.node.getAttribute('module') == symbol.sourceModule:
					logging.debug("decl added for %s" %(symbol))
					additionalDeclarations.append(symbol)
				elif (symbol.analysis and symbol.analysis.isModuleSymbol) \
				or (isModuleSymbol and currRoutine.node.getAttribute('module') != symbol.sourceModule) \
				or symbol.declarationType == DeclarationType.FOREIGN_MODULE_SCALAR:
					if symbol.sourceModule != callee.parentModule.name:
						foreignModuleNode = moduleNodesByName[symbol.sourceModule]
						symbol.loadImportInformation(parentNode.ownerDocument, foreignModuleNode)
					logging.debug("import added for %s" %(symbol))
					additionalImports.append(symbol)
				elif symbol.declarationType in [
					DeclarationType.LOCAL_ARRAY,
					DeclarationType.LOCAL_SCALAR,
					DeclarationType.OTHER_SCALAR
				]:
					logging.debug("dummy added for %s" %(symbol))
					additionalDummies.append(symbol)
			return additionalImports, additionalDeclarations, additionalDummies

		if callee.node.getAttribute("parallelRegionPosition") != "within" or not callee.parallelRegionTemplates:
			return [], [], []
		if not hasattr(callee.parentModule, "node") or not callee.parentModule.node:
			raise Exception("calling a kernel %s directly from a foreign module is not supported. Use splitting instead." %(
				callee.name
			))
		argumentSymbolNames = []
		for argument in callee.programmerArguments:
			argumentMatch = self.patterns.callArgumentPattern.match(argument)
			if not argumentMatch:
				raise UsageError("illegal argument: %s" %(argument))
			argumentSymbolNames.append(argumentMatch.group(1))
		logging.debug("============ loading additional symbols for module %s ===============" %(callee.parentModule.name))
		moduleImports, moduleDeclarations, additionalDummies = getAdditionalImportsAndDeclarationsForParentScope(callee.parentModule.node, argumentSymbolNames)
		if len(additionalDummies) != 0:
			raise Exception("dummies are not supposed to be added for module scope symbols: %s; type of first: %i" %(
				additionalDummies,
				additionalDummies[0].declarationType
			))
		indexedModuleSymbols = (
			indexSymbolsByNameInScope(moduleImports),
			indexSymbolsByNameInScope(moduleDeclarations)
		)
		logging.debug("============ loading additional symbols for routine %s ==============" %(callee.node.getAttribute("name")))
		routineImports, routineDeclarations, additionalDummies = getAdditionalImportsAndDeclarationsForParentScope(callee.node, argumentSymbolNames)
		mergeSymbols(routineImports, indexedModuleSymbols[0])
		mergeSymbols(routineDeclarations, indexedModuleSymbols[1])
		mergeSymbols(additionalDummies, indexedModuleSymbols[0])
		mergeSymbols(additionalDummies, indexedModuleSymbols[1])
		for symbol in routineImports + indexedModuleSymbols[0].values() + routineDeclarations + indexedModuleSymbols[1].values() + additionalDummies:
			symbol.isPresent = True
		return (
			sorted(routineImports + indexedModuleSymbols[0].values()),
			sorted(routineDeclarations + indexedModuleSymbols[1].values()),
			sorted(additionalDummies)
		)

	def getIterators(self, parallelRegionTemplate):
		if not appliesTo(["GPU"], parallelRegionTemplate):
			return []
		return [domain.name for domain in getDomainsWithParallelRegionTemplate(parallelRegionTemplate)]

	def subroutinePrefix(self, routineNode):
		parallelRegionPosition = routineNode.getAttribute("parallelRegionPosition")
		if not parallelRegionPosition or parallelRegionPosition == "" or parallelRegionPosition == "inside":
			return ""
		elif parallelRegionPosition == "within":
			return "attributes(global)"
		elif parallelRegionPosition == "outside":
			return "attributes(device)"
		else:
			raise UsageError("invalid parallel region position defined for this routine: %s" %(parallelRegionPosition))

	def subroutineCallInvocationPrefix(self, subroutineName, parallelRegionTemplate):
		return 'call %s' %(subroutineName)

	def subroutineExitPoint(self, dependantSymbols, routineIsKernelCaller, isSubroutineEnd):
		if isSubroutineEnd:
			self.currRoutineNode = None
		return super(CUDAFortranImplementation, self).subroutineExitPoint( dependantSymbols, routineIsKernelCaller, isSubroutineEnd)

	def iteratorDefinitionBeforeParallelRegion(self, domains):
		if len(domains) > 3:
			raise UsageError("Only up to 3 parallel dimensions supported. %i are specified: %s." %(len(domains), str(domains)))
		cudaDims = ("x", "y", "z")
		result = ""
		for index, domain in enumerate(domains):
			startsAt = domain.startsAt if domain.startsAt != None else "1"
			result += "%s = (blockidx%%%s - 1) * blockDim%%%s + threadidx%%%s + %s - 1\n" %(
				domain.name,
				cudaDims[index],
				cudaDims[index],
				cudaDims[index],
				startsAt
			)
		return result

	def safetyOutsideRegion(self, domains):
		result = "if ("
		for index, domain in enumerate(domains):
			endsAt = domain.endsAt if domain.endsAt != None else domain.size
			if index != 0:
				result += " .OR. "
			result += "%s .GT. %s" %(domain.name, endsAt)
		result += ") then\nreturn\nend if\n"
		return result

	def parallelRegionBegin(self, dependantSymbols, parallelRegionTemplate):
		if not dependantSymbols:
			raise UsageError("parallel region without any dependant arrays")
		domains = getDomainsWithParallelRegionTemplate(parallelRegionTemplate)
		regionStr = self.iteratorDefinitionBeforeParallelRegion(domains)
		regionStr += self.safetyOutsideRegion(domains)
		return regionStr

	def parallelRegionEnd(self, parallelRegionTemplate, routine, skipDebugPrint=False):
		return ""

	def declarationEnd(self, dependantSymbols, routineIsKernelCaller, currRoutineNode, currParallelRegionTemplates):
		self.currRoutineNode = currRoutineNode
		result = ""
		if 'DEBUG_PRINT' in self.optionFlags:
			result += "real(8) :: hf_output_temp\n"
		result += getIteratorDeclaration(currRoutineNode, currParallelRegionTemplates, ["GPU"])

		if routineIsKernelCaller:
			result += "type(dim3) :: cugrid, cublock\n"
			result += "integer(4) :: cugridSizeX, cugridSizeY, cugridSizeZ, cuerror, cuErrorMemcopy\n"

		result += self.declarationEndPrintStatements()
		result += super(CUDAFortranImplementation, self).declarationEnd(
			dependantSymbols,
			routineIsKernelCaller,
			currRoutineNode,
			currParallelRegionTemplates
		)
		return result

	def additionalIncludes(self):
		return "use cudafor\n"

class DebugCUDAFortranImplementation(CUDAFortranImplementation):

	def kernelCallPreparation(self, parallelRegionTemplate, calleeNode=None):
		result = CUDAFortranImplementation.kernelCallPreparation(self, parallelRegionTemplate, calleeNode)
		if calleeNode != None:
			iterators = self.getIterators(parallelRegionTemplate)
			gridSizeVarNames = ["cugridSizeX", "cugridSizeY", "cugridSizeZ"]
			routineName = calleeNode.getAttribute('name')
			result += "write(0,*) 'calling kernel %s with grid size', " %(routineName)
			for i in range(len(iterators)):
				if i != 0:
					result += ", "
				result += "%s" %(gridSizeVarNames[i])
			result += "\n"
		return result

	def kernelCallPost(self, symbolsByName, calleeRoutineNode):
		result = CUDAFortranImplementation.kernelCallPost(self, symbolsByName, calleeRoutineNode)
		if calleeRoutineNode.getAttribute('parallelRegionPosition') != 'within':
			return result
		result += "if(cuerror .NE. cudaSuccess) then\n"\
				"\tstop 1\n" \
			"end if\n"
		return result

	def declarationEndPrintStatements(self):
		if self.currRoutineNode.getAttribute('parallelRegionPosition') != 'inside':
			return ""
		result = CUDAFortranImplementation.declarationEndPrintStatements(self)
		routineName = self.currRoutineNode.getAttribute('name')
		result += "write(0,*) 'entering subroutine %s'\n" %(routineName)
		return result

class DebugEmulatedCUDAFortranImplementation(DebugCUDAFortranImplementation):
	def __init__(self, optionFlags):
		DebugCUDAFortranImplementation.__init__(self, optionFlags)

	def parallelRegionBegin(self, dependantSymbols, parallelRegionTemplate):
		if not dependantSymbols:
			raise UsageError("parallel region without any dependant arrays")
		domains = getDomainsWithParallelRegionTemplate(parallelRegionTemplate)
		regionStr = self.iteratorDefinitionBeforeParallelRegion(domains)
		routineName = self.currRoutineNode.getAttribute('name')
		if not routineName:
			raise Exception("Routine name undefined.")
		iterators = self.getIterators(parallelRegionTemplate)
		if not iterators or len(iterators) == 0:
			raise UsageError("No iterators in kernel.")
		error_conditional = "("
		for i in range(len(iterators)):
			if i != 0:
				error_conditional += " .OR. "
			error_conditional += "%s .LT. 1" %(iterators[i])
		error_conditional = error_conditional + ")"
		regionStr += "if %s then\n\twrite(0,*) 'ERROR: invalid initialization of iterators in kernel \
%s - check kernel domain setup'\n" %(error_conditional, routineName)
		regionStr += "\twrite(0,*) "
		for i in range(len(iterators)):
			if i != 0:
				regionStr += ", "
			regionStr += "'%s', %s" %(iterators[i], iterators[i])
		regionStr += "\nend if\n"
		conditional = "("
		for i in range(len(iterators)):
			if i != 0:
				conditional = conditional + " .AND. "
			conditional = conditional + "%s .EQ. %i" %(iterators[i], 1)
		conditional = conditional + ")"
		regionStr += "if %s write(0,*) '*********** entering kernel %s finished *************** '\n" %(conditional, routineName)
		region_domains = getDomainsWithParallelRegionTemplate(parallelRegionTemplate)
		for symbol in dependantSymbols:
			offsets = []
			symbol_domain_names = [domain[0] for domain in symbol.domains]
			for region_domain in region_domains:
				if region_domain.name in symbol_domain_names:
					offsets.append(region_domain.startsAt if region_domain.startsAt != None else "1")
			for i in range(len(symbol.domains) - len(offsets)):
				offsets.append("1")
			if symbol.intent == "in" or symbol.intent == "inout":
				symbol_access = symbol.accessRepresentation(iterators, offsets, parallelRegionTemplate)
				regionStr += "if %s then\n\twrite(0,*) '%s', %s\nend if\n" %(conditional, symbol_access, symbol_access)

		regionStr += "if %s write(0,*) '**********************************************'\n" %(conditional)
		regionStr += "if %s write(0,*) ''\n" %(conditional)
		regionStr += self.safetyOutsideRegion(domains)
		return regionStr