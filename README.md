# tab-compare
TabCompare is a visual comparison tool to understand differences in dashboards across different versions of Tableau Server.  It uses ImageMagick Studio LLC.  


----------------------
TabCompare Version 2.0
----------------------
TabCompare is a command line utility to help compare the format of Tableau content on 2x separate Tableau Server instances. 
TabCompare is designed to help identify any formatting differences between different versions of Tableau Sever.


----------------------
Instructions
----------------------
Install ImageMagick. If using the Python file, install the required modules. Prep your Tableau Server instances by using two non-production servers running two different versions of Tableau Server. Turn off all background tasks and take a backup from the first. Restore it to the second.
Now, run TabCompare against both servers using the command-line syntax below. Once complete, open TabCompare.twbx, edit the connection, and point to the report.csv that was generated. Review the list of differences found, if any. See bottom of this document for a list of commonly encountered difference types.


----------------------
File list
----------------------
ImageMagick-6.9.9-51-Q8-x64-dll.exe	ImageMagick Windows Libraries. Must be installed First!

TabCompare.exe				TabCompare Command Line Executable

TabCompare.py				TabCompare Python Source Code

log.py						TacCompare logging module

TabCompare.twbx				TabCompare Tableau Workbook to Analyse Results


----------------------
Command Line Arguments
----------------------
--sa                     Server A URL (the target/new version of Tableau Server)

--sb                     Server B URL (the old version of Tableau Server)

--u              	     Tableau Server Username

--p  (optional)          Tableau Server Password. USER WILL BE PROMPTED FOR PASSWORD IF NOT PROVIDED

--f                      Filepath to save the image returned. EXITING FILES IN FILEPATH WILL BE DELETED

--l  (optional)          Log file. Date and ".log" will be appended automatically to allow for rotation.
                         Defaults to \logs in the folder it is run from.
                         
--ll  (optional)         Log level. Default value: 'ERROR'. Possible values: 'ERROR', 'WARN', 'INFO', 'DEBUG'

--si (optional)      	 Site Name Filter

--pi (optional)      	 Project Name Filter

--wi (optional)     	 Workbook Name Filter

--vi (optional)     	 View List Filter (provide path to input csv containing view LUIDs)

--cm (optional)		     Compare metrics type. Default value: 'peak_signal_to_noise_ratio'. Possible values: 'undefined', 'absolute', 'mean_absolute', 'mean_error_per_pixel', 'mean_squared', 'normalized_cross_correlation', 'peak_absolute', 'peak_signal_to_noise_ratio', 'perceptual_hash', 'root_mean_square'

--mm (optional)     	 Match method (how views will be matched from server A to server B.
                         Note that this also informs output directory structure naming convention.
                         Valid choices: 'content_url' or 'luid'
                         
--cv (optional)     	 Compare views visually based on image exports (required if not using --cd)

--cd (optional)     	 Compare views by based on summary data exports (required if not using --cv)

--nt (optional)     	 Number of threads to run (total vizzes being rendered on each server simultaneously)

--nr (optional)     	 Number of retries to attempt for rendering errors or for found differences (reduces false positives)


If none of the optional filter flags are provided it will get all views for all sites on your server
For more information on Compare Metrics please see https://www.imagemagick.org/Usage/compare/


----------------------
Common Differences Found
----------------------

Reasons found for legitimate differences:


Floating point rounding differences, e.g. 0.661757812 vs 0.661757813

Random functions being in jitter plots

Data differences due to live connections against frequently-changing data (this should occur rarely, due to TabCompare starting viz renders on both servers at the same time, but can still occur)

Dashboard differences due to "Data Update Time" being used in a Title or Caption (this should also be rare, for the same reason)

Casing and collation differences can arise from arbitrary sort orders on text fields


----------------------
Additional Information
----------------------

For example to get all views in the “Greatest Hits” project on a site called “TableauJunkie”, run the following:
TabCompare.exe --sa http://tabserverA.tableaujunkie.com:8000 --sb http://tabserverB.tableaujunkie.com:8000 --u admin --f C:\TabCompare\Images --pi "Greatest Hits" --si TableauJunkie

Or to get all views in the “Google Analytics” workbook on a site called “TableauJunkie” using the mean_absolute compare metric, run the following:
TabCompare.exe --sa http://tabserverA.tableaujunkie.com:8000 --sb http://tabserverB.tableaujunkie.com:8000 --u admin --f C:\TabCompare\Images --wi "Google Analytics" --si TableauJunkie --cm mean_absolute
