# -*- coding: utf-8 -*-
#!/usr/bin/env python

import os, gzip, glob, time
import argparse
from multiprocessing.dummy import Pool as ThreadPool

"""
Created on Thu Jan 28 10:58:33 2016
Laste Modified on Sat Feb 6 11:11:11 2016

Description: ORFSNuPer uses identified SNPs from the 1000 Genomes Project that meet certain MAF criteria related to a given population. From that SNP, the hg19 reference genome is indexed with regard to the identified SNP and looks to see if a potential ORF was created. IFF an ORF is identified, ORFSNuPer looks upstream and downstream for stop codons. IFF a potential novel reading frame is found, using reads from RNA-seq and ribosomal profiling data, ORFSNuPer will check to see if transcription and/or translation occurs.
@author: Marcus D. Sherman
@email: mdsherm@umich.edu
"""
startTime, startasc = time.time(), time.asctime()

######ARGPARSE START######
parser = argparse.ArgumentParser(description = 'Finds novel ORFs dues to SNPs')
    #define where the reference sequence is
parser.add_argument('-r', action = 'store', dest = 'ref',  help = 'Directory of reference chromosomes', default = '/home/mdsherm/Project/Reference/hg19/Sequence/Chromosomes')
    #define what VCF file you will be working from
parser.add_argument('-v', action = 'store', dest = 'vcf',  help = 'Path/to/<vcf.gz>', default = '/home/mdsherm/Project/YRI_vcfsubsets/chr6.recode.vcf.gz')
    #how many nucleotides do you want to look upstream and downstream of potential ORFs
parser.add_argument('-t', action = 'store', dest = 'threshold', type = int, help = 'Up/downstream threshold', default = 3000)
    #Define your output filename and directory
parser.add_argument('-o', action = 'store', dest = 'output', help = 'Set output filename', default = '/home/mdsherm/Project/SNuPer_results/pythonTest')
    #Where are the ribosome profiling BAM files
parser.add_argument('--ribosome', action = 'store', dest = 'ribo', help = 'Directory of Ribosomal BAM files', default = '/home/mdsherm/Rotation/ribosomal/bwa_alignment' )
    #Where are the RNA-seq BAM files
parser.add_argument('--rna', action = 'store', dest = 'rna', help = 'Directory of RNA BAM files', default = '/home/mdsherm/Rotation/RNA_fq/tophat_hg19')
args = parser.parse_args()
vcf = args.vcf
riboDir = args.ribo
RNADir = args.rna
outfile = args.output
reference = args.ref
threshold = args.threshold
######ARGPARSE END######

###CODONS START###
negStops = ['TTA','CTA','TCA']
negStart = "CAT"
plusStops = ['ATT','ATC','ACT']
plusStart = "TAC"
###CODONS END###

#makes lists of all RNA-seq and ribosome profiling BAM files
RNAbams, Ribobams = [],[]
os.chdir(RNADir)
for dir,_,_ in os.walk(os.getcwd()):
    RNAbams.extend(glob.glob(os.path.join(dir,"*hits.bam")))
os.chdir(riboDir)
for dir,_,_ in os.walk(os.getcwd()):
    Ribobams.extend(glob.glob(os.path.join(dir,"*sort.bam")))

class potORF(object):

    """Create an potential ORF object with the following attributes:

    chrom: identifies which chromosome the potential ORF is on
    start: position of the first nt in start codon
    end: postion of the last nt in the start codon
    strand: (+) or (-) strand
    up: upstream UTR of potential ORF
    upCheck: is there an upstream stop
    down: downstream sequence of potential ORF
    downCheck: is there a downstream stop
    up/downPos: how many codons away is a given stop codon (relative to strand)
    """

    #instantiate potential ORF object and get upstream and downstream sequences
    def __init__(self, CHROM, START, END, STRAND):
        self.chrom = CHROM
        self.start = START
        self.end = END
        self.strand = STRAND
        self.up = os.popen('samtools faidx %s/chr%s.fa chr%s:%d-%d' %(reference, self.chrom, self.chrom, int(self.start)-threshold, int(self.start)-1))
        self.up.readline()
        self.up = ((self.up.read()).rstrip()).upper()
        self.down = os.popen('samtools faidx %s/chr%s.fa chr%s:%d-%d' %(reference, self.chrom, self.chrom, int(self.end)+1, int(self.end)+threshold))
        self.down.readline()
        self.down = ((self.down.read()).rstrip()).upper()
        self.upcheck = False
        self.downcheck = False
        self.upPos = []
        self.downPos = []
        self.RNAcount = None
        self.ribocount = None

    #check to see if a stop codon is within upstream sequence (downstream if (-) strand)
    def lookUp(self):
        codonCount = 0
        if self.strand == True:
            stops = plusStops
        else:
            stops = negStops
        for i in range(0,threshold,3):
           codon = self.up[i:i+3]
           codonCount += 1
           if any(string in codon for string in stops):
               self.upcheck = True
               self.upPos.extend([codonCount,])
        return self

    #check to see if a stop codon is within downsteam sequence (upstream if (-) strand)
    def lookDown(self):
        codonCount = 0
        if self.strand == True:
            stops = plusStops
        else:
            stops = negStops
        for i in range(0,threshold,3):
           codon = self.down[i:i+3]
           codonCount += 1
           if any(string in codon for string in stops):
               self.downcheck = True
               self.downPos.extend([codonCount,])
        return self

    #Looks at all specified BAM files and determine the number of reads found in a given region.
    def WordCount(self):
        if self.upcheck == True and  self.downcheck == True:
           if self.strand == True: #is it a (+) strand?
               self.RNAcount = readCheck(True, int(self.chrom), int(self.start), int(self.start+int(self.downPos[0])*3 ))
               if self.RNAcount == (None or 0):
                   pass
               else:
                   self.ribocount = readCheck(False, int(self.chrom), int(self.start), int(self.start+int(self.downPos[0])*3 ))
           else:
               self.RNAcount = readCheck(True, int(self.chrom), int(self.start-int(self.upPos[-1])*3), int(self.start))
               if self.RNAcount == (None or  0):
                   pass
               else:
                   self.ribocount = readCheck(False, int(self.chrom), int(self.start-int(self.upPos[-1])*3), int(self.start))

#Used to iterate potential ORF class instantiation
def portORF(CHROM, START, END, STRAND):
    portORF = potORF(CHROM, START, END, STRAND)
    return portORF

#iteratively pulls read count over a given region across all BAMs
def readCheck(RNAorRIBO, CHROM, START, STOP):
    bamlist = []
    WC = []
    typeCheck = RNAorRIBO
    if typeCheck == True: #True = RNA-seq, False = Ribosome profiling
        bamlist = RNAbams
    elif typeCheck == False:
        bamlist = Ribobams
    for f in bamlist:
        readcount = os.popen('samtools view -q 10 '+f+' chr%d:%d-%d | wc -l' %(int(CHROM), int(START), int(STOP)))
        count = int(readcount.readline().rstrip())
        WC.extend([count])
    if sum(WC) == 0:
        return None
    else:
        return round(float(sum(WC))/int(len(WC)),3)

#function identifies SNPs, extracts sequence from reference +/-2 nt and looks for start codon within sequence
def ORFSNuper():
    global potORFs
    potORFs = []
#    global orfcount
#    orfcount = 0 #use when debugging
    with gzip.open(vcf,'rt')as file:
#        while orfcount < 15:  #use when debugging
        for line in file:
            #skip all of the lines before content
            if "#" in line:
                continue
            else:
                columns = line.split()

                #Check to see if it is a SNP
                if len(columns[3]) and len(columns[4]) == 1:

                    #look for the reference sequence around SNP
                    seq = os.popen('samtools faidx %s/chr%s.fa chr%s:%d-%d' %(reference,columns[0],columns[0],int(columns[1])-1,int(columns[1])+2))
                    seq.readline()
                    seq = seq.read().rstrip()
                    seq_step = (seq[:1]+ columns[4]+ seq[3:]).upper()

                    #Check to see if (+) strand ORF is found
                    if plusStart in seq_step:
                        posCheck = str.find(seq_step, plusStart)+1
                        if 1 <= posCheck < 3:
                            seqPos = int(columns[1])-posCheck
                        elif posCheck > 3:
                            seqPos = int(columns[1])+posCheck
                        else:
                            pass
                            #Create potential ORF class instance
                        potORFs.extend([portORF(columns[0], seqPos, seqPos+2, True)])
#                        orfcount += 1 #use when debugging

                        #Check to see if (-) strand ORF is found
                        if negStart in seq_step:
                            posCheck = str.find(seq_step, negStart)+1
                            if 1 <= posCheck < 3:
                                seqPos = int(columns[1])+posCheck
                            elif posCheck > 3:
                                seqPos = int(columns[1])-posCheck
                            else:
                                pass
                            #Create potential ORF class instance
                            potORFs.extend([portORF(columns[0], seqPos, seqPos-2, False)])
#                            orfcount += 1 #use when debugging
                        else:
                            continue
                    #For debugging
#                    if orfcount >= 15:
#                        print("orfcount met!")
#                        break

#Find the potential ORFs
ORFSNuper()

#Look upstream and downstream for stop codons and read count of ribosome/RNA bam files via class instance multithreading
pool = ThreadPool()
pool.map(lambda obj: obj.lookUp().lookDown().WordCount(), potORFs)
pool.close()
pool.join()

#Using the joined instances of potential ORFs, cleans & coalesces the data for output
SNuPed = []
for i in range(len(potORFs)):
    if potORFs[i].upcheck == True and  potORFs[i].downcheck == True: #does it have an up/downstream stop?
        if potORFs[i].RNAcount == (0 or None):
	    continue
	else:
            if potORFs[i].strand ==True: #is it a (+) strand?
            	#if there were RNA-seq reads, check for Ribosome profiling reads (translation)
            	SNuPed.extend(['\t'.join([str(potORFs[i].chrom), "+", str(potORFs[i].start), str(potORFs[i].start+int(potORFs[i].downPos[0])*3 ), str(potORFs[i].RNAcount), str(potORFs[i].ribocount)])])
            else:
            	SNuPed.extend(['\t'.join([str(potORFs[i].chrom), "-", str(potORFs[i].start), str(potORFs[i].start-int(potORFs[i].upPos[-1])*3 ), str(potORFs[i].RNAcount),str(potORFs[i].ribocount) ])])

    else:
	continue
#find out how long the process took
endTime, endasc = time.time(), time.asctime()
m,s = divmod(endTime-startTime,60)
h,m = divmod(m,60)
d,h = divmod(h,24)

#Print the list of potential ORFs in a tab-delimited file
with open(outfile,'w') as f:
    print >> f,"\t".join(["CHROM","STRAND","START", "Nearest_STOP", "RNA_ReadCount", "Ribo_ReadCount"])
    print >> f,"\n".join(SNuPed)

#Write a small report for start time, end time, and elapsed time
with open(outfile+".log",'w') as f:
    print >> f, "Program started:"
    print >> f, startasc
    print >> f, ""
    print >> f, "Program completed:"
    print >> f, endasc
    print >> f, ""
    print >> f, "Elapsed time:"
    print >> f, str(d)+" days", str(h)+" hours",str(m)+" minutes", str(round(s,2))+" seconds"