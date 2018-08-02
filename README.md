# tab-compare
TabCompare is a visual comparison tool to understand differences in dashboards across different versions of Tableau Server.  It uses ImageMagick Studio LLC.  

----------------------
TabCompare Version 1.3
----------------------
TabCompare is a command line utility to help compare the format of Tableau content on 2x separate Tableau Server instances. 
TabCompare is designed to help identify any formatting differences between different versions of Tableau Sever.

----------------------
File list
----------------------
ImageMagick-6.9.9-51-Q8-x64-dll.exe	ImageMagick Windows Libraries. Must be installed First!

TabCompare.exe				TabCompare Command Line Executable

TabCompare.py				TabCompare Python Source Code

TabCompare.twbx				TabCompare Tableau Workbook to Analyse Results


----------------------
Command Line Arguments
----------------------
--sa                     Server A URL (the target/new version of Tableau Server)

--sb                     Server B URL (the old version of Tableau Server)

--u              	 Tableau Server Username

--p (optional)           Tableau Server Password. USER WILL BE PROMPTED FOR PASSWORD IF NOT PROVIDED

--f                      Filepath to save the image returned. EXITING FILES IN FILEPATH WILL BE DELETED

--si (optional)      	 Site Name Filter

--pi (optional)      	 Project Name Filter

--wi (optional)     	 Workbook Name Filter

--cm (optional)		 Compare metrics type. Default value: 'peak_signal_to_noise_ratio'. Possible values: 'undefined', 'absolute', 'mean_absolute', 'mean_error_per_pixel', 'mean_squared', 'normalized_cross_correlation', 'peak_absolute', 'peak_signal_to_noise_ratio', 'perceptual_hash', 'root_mean_square'


If none of the optional flags are provided it will get all views for all sites on your server
For more information on Compare Metrics please see https://www.imagemagick.org/Usage/compare/

----------------------
Additional Information
----------------------

For example to get all views in the “Greatest Hits” project on a site called “TableauJunkie”, run the following:
TabCompare.exe --sa http://tabserverA.tableaujunkie.com:8000 --sb http://tabserverB.tableaujunkie.com:8000 --u admin --f C:\TabCompare\Images --pi "Greatest Hits" --si TableauJunkie

Or to get all views in the “Google Analytics” workbook on a site called “TableauJunkie” using the mean_absolute compare metric, run the following:
TabCompare.exe --sa http://tabserverA.tableaujunkie.com:8000 --sb http://tabserverB.tableaujunkie.com:8000 --u admin --f C:\TabCompare\Images --wi "Google Analytics" --si TableauJunkie --cm mean_absolute

----------------------
Changes
----------------------

v1.3 - fixed 'SSL: CERTIFICATE_VERIFY_FAILED' issue when conecting to Tableau Server with SSL enabled
