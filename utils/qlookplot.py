import numpy as np
import matplotlib.pyplot as plt
import os, sys
# from config import get_and_create_download_dir
import shutil
from astropy.io import fits
import urllib2
from split_cli import split_cli as split
from ptclean_cli import ptclean_cli as ptclean
from suncasa.utils import helioimage2fits as hf
import sunpy
import sunpy.map as smap
from astropy import units as u
from astropy.time import Time
from astropy.io import fits
from taskinit import ms, tb, qa, iatool
from tclean_cli import tclean_cli as tclean
from matplotlib.dates import DateFormatter
from astropy.io import fits
from astropy.coordinates import SkyCoord
import pickle
import datetime
import matplotlib as mpl
import matplotlib.cm as cm
import sunpy.cm.cm as cm_sunpy
import matplotlib.colors as colors
import matplotlib.patches as patches
from matplotlib import gridspec
import glob
from suncasa.utils import DButil
import copy
from pkg_resources import parse_version
# import pdb
import time
from mpl_toolkits.axes_grid1 import make_axes_locatable
from suncasa.utils import plot_mapX as pmX
import warnings


def warn(*args, **kwargs):
    pass


warnings.warn = warn


def get_goes_data(t=None, sat_num=None):
    ''' Reads GOES data from https://umbra.nascom.nasa.gov/ repository, for date
        and satellite number provided.  If sat_num is None, data for all available
        satellites are downloaded, with some sanity check used to decide the best.
        If the Time() object t is None, data for the day before the current date
        are read (since there is a delay of 1 day in availability of the data).

        Returns:
           goes_t    GOES time array in plot_date format
           goes_data GOES 1-8 A lightcurve
        '''
    from sunpy.util.config import get_and_create_download_dir
    import shutil
    from astropy.io import fits
    import urllib2
    import ssl
    if t is None:
        t = Time(Time.now().mjd - 1, format='mjd')
    yr = t.iso[:4]
    datstr = t.iso[:10].replace('-', '')
    context = ssl._create_unverified_context()
    if sat_num is None:
        f = urllib2.urlopen('https://umbra.nascom.nasa.gov/goes/fits/' + yr, context=context)
        lines = f.readlines()
        sat_num = []
        for line in lines:
            idx = line.find(datstr)
            if idx != -1:
                sat_num.append(line[idx - 2:idx])
    if type(sat_num) is int:
        sat_num = [str(sat_num)]
    filenames = []
    for sat in sat_num:
        filename = 'go' + sat + datstr + '.fits'
        url = 'https://umbra.nascom.nasa.gov/goes/fits/' + yr + '/' + filename
        f = urllib2.urlopen(url, context=context)
        with open(get_and_create_download_dir() + '/' + filename, 'wb') as g:
            shutil.copyfileobj(f, g)
        filenames.append(get_and_create_download_dir() + '/' + filename)
    pmerit = 0
    for file in filenames:
        gfits = fits.open(file)
        data = gfits[2].data['FLUX'][0][:, 0]
        good, = np.where(data > 1.e-8)
        tsecs = gfits[2].data['TIME'][0]
        merit = len(good)
        date_elements = gfits[0].header['DATE-OBS'].split('/')
        if merit > pmerit:
            print('File:', file, 'is best')
            pmerit = merit
            goes_data = data
            goes_t = Time(date_elements[2] + '-' + date_elements[1] + '-' + date_elements[0]).plot_date + tsecs / 86400.
    try:
        return goes_t, goes_data
    except:
        print('No good GOES data for', datstr)
        return None, None


def msclearhistory(msfile):
    from taskinit import tb
    tb.open(msfile + '/HISTORY', nomodify=False)
    nrows = tb.nrows()
    if nrows > 0:
        tb.removerows(range(nrows))
    tb.close()


aiadir_default = '/srg/data/sdo/aia/level1/'


def get_mapcube_time(mapcube):
    from astropy.time import Time
    t = []
    for idx, mp in enumerate(mapcube):
        if mp.meta.has_key('t_obs'):
            tstr = mp.meta['t_obs']
        else:
            tstr = mp.meta['date-obs']
        t.append(tstr)
    return Time(t)


def uniq(lst):
    last = object()
    nlst = []
    for item in lst:
        if item == last:
            continue
        nlst.append(item)
        last = item
    return nlst


def downloadAIAdata(trange, wavelength=None, outdir='./'):
    if isinstance(trange, list) or isinstance(trange, tuple) or type(trange) == np.ndarray or type(trange) == Time:
        if len(trange) != 2:
            raise ValueError('trange must be a number or a two elements array/list/tuple')
        else:
            trange = Time(trange)
            if trange.jd[1] < trange.jd[0]:
                raise ValueError('start time must be occur earlier than end time!')
            else:
                [tst, ted] = trange
    else:
        [tst, ted] = Time(trange.jd + np.array([-1., 1.]) / 24. / 3600 * 6.0, format='jd')

    if wavelength == None:
        wavelength = [171]
    elif type(wavelength) is str:
        if wavelength.lower() == 'all':
            wavelength = [94, 131, 171, 193, 211, 304, 335, 1600, 1700]
        else:
            wavelength = [float(wavelength)]
    elif type(wavelength) is float or type(wavelength) is int:
        wavelength = [wavelength]
    wavelength = [float(ll) for ll in wavelength]
    if ted.mjd <= tst.mjd:
        print('Error: start time must occur earlier than end time. please re-enter start time and end time!!!')

    nwave = len(wavelength)
    print('{} passbands to download'.format(nwave))
    from sunpy.net import vso
    client = vso.VSOClient()
    for widx, wave in enumerate(wavelength):
        wave1 = wave - 3.0
        wave2 = wave + 3.0
        print('{}/{} Downloading  AIA {:.0f} data ...'.format(widx + 1, nwave, wave))
        qr = client.query(vso.attrs.Time(tst.iso, ted.iso), vso.attrs.Instrument('aia'),
                          vso.attrs.Wave(wave1 * u.AA, wave2 * u.AA))
        res = client.get(qr, path='{file}').wait()

        for ll in res:
            vsonamestrs = ll.split('_')
            if vsonamestrs[2].startswith('1600') or vsonamestrs[2].startswith('1700'):
                product = 'aia.lev1_uv_24s'
            else:
                product = 'aia.lev1_euv_12s'
            jsocnamestr = product + '.' + '{}-{}-{}{}{}Z.'.format(vsonamestrs[3], vsonamestrs[4], vsonamestrs[5],
                                                                  vsonamestrs[6],
                                                                  vsonamestrs[7]).upper() + vsonamestrs[2][
                                                                                            :-1] + '.image_lev1.fits'
            print(ll, jsocnamestr)
            os.system('mv {} {}/{}'.format(ll, outdir, jsocnamestr))
    if os.path.exists('/tmp/suds/'):
        os.system('rm -rf /tmp/suds/')


def trange2aiafits(trange, aiawave, aiadir):
    trange = Time(trange)
    if len(trange.iso) == 2:
        if trange[1].jd - trange[0].jd < 12. / 24. / 3600:
            trange = Time(np.mean(trange.jd) + np.array([-1., 1.]) * 6. / 24. / 3600, format='jd')
    aiafits = DButil.readsdofile(datadir=aiadir_default, wavelength=aiawave, trange=trange, isexists=True)
    if not aiafits:
        aiafits = DButil.readsdofileX(datadir='./', wavelength=aiawave, trange=trange, isexists=True)
    if not aiafits:
        aiafits = DButil.readsdofileX(datadir=aiadir, wavelength=aiawave, trange=trange, isexists=True)
    if not aiafits:
        downloadAIAdata(trange, wavelength=aiawave)
        aiafits = DButil.readsdofileX(datadir='./', wavelength=aiawave, trange=trange, isexists=True)
    return aiafits


def mk_qlook_image(vis, ncpu=10, timerange='', twidth=12, stokes='I,V', antenna='', imagedir=None, spws=[], toTb=True,
                   overwrite=True, doslfcal=False,
                   phasecenter='', robust=0.0, niter=500, imsize=[512], cell=['5.0arcsec'], reftime='', mask='',
                   uvrange='',
                   c_external=True):
    vis = [vis]
    subdir = ['/']

    for idx, f in enumerate(vis):
        if f[-1] == '/':
            vis[idx] = f[:-1]

    if not imagedir:
        imagedir = './'
    msfile = vis[0]
    ms.open(msfile)
    metadata = ms.metadata()
    observatory = metadata.observatorynames()[0]
    imres = {'Succeeded': [], 'BeginTime': [], 'EndTime': [], 'ImageName': [], 'Spw': [], 'Vis': [], 'Freq': [],
             'Obs': []}
    # axisInfo = ms.getdata(["axis_info"], ifraxis=True)
    spwInfo = ms.getspectralwindowinfo()
    # freqInfo = axisInfo["axis_info"]["freq_axis"]["chan_freq"].swapaxes(0, 1) / 1e9
    # freqInfo_ravel = freqInfo.ravel()
    ms.close()
    nspw = len(spwInfo)
    if not spws:
        if observatory == 'EVLA':
            spws = list(np.arange(nspw).astype(str))
        if observatory == 'EOVSA':
            spws = ['1~5', '6~10', '11~15', '16~25']
    if observatory == 'EOVSA':
        if stokes != 'XX,YY':
            print('Provide stokes: ' + str(stokes) + '. However EOVSA has linear feeds. Force stokes to be XX,YY')
            stokes = 'XX,YY'

    # pdb.set_trace()
    msfilebs = os.path.basename(msfile)
    imdir = imagedir + subdir[0]
    if not os.path.exists(imdir):
        os.makedirs(imdir)
    if doslfcal:
        slfcalms = './' + msfilebs + '.rr'
        split(msfile, outputvis=slfcalms, datacolumn='corrected', correlation='RR')
    for spw in spws:
        spwran = [s.zfill(2) for s in spw.split('~')]
        # freqran = [
        #     (int(s) * spwInfo['0']['TotalWidth'] + spwInfo['0']['RefFreq'] + spwInfo['0']['TotalWidth'] / 2.0) / 1.0e9
        #     for s in spw.split('~')]
        spw_ = spw.split('~')
        if len(spw_) == 2:
            freqran = [(spwInfo['{}'.format(s)]['RefFreq'] + spwInfo['{}'.format(s)]['TotalWidth'] / 2.0) / 1.0e9 for s
                       in spw.split('~')]
        elif len(spw_) == 1:
            s = spw_[0]
            freqran = np.array([0, spwInfo['{}'.format(s)]['TotalWidth']]) + spwInfo['{}'.format(s)]['RefFreq']
            freqran = freqran / 1.0e9
            freqran = list(freqran)
        else:
            raise ValueError("Keyword 'spw' in wrong format")

        cfreq = np.mean(freqran)
        bmsz = max(30. / cfreq, 30.)
        uvrange = '<3km'

        if cell == ['5.0arcsec'] and imsize == [512]:
            if cfreq < 10.:
                imsize = 512
                cell = ['5arcsec']
            else:
                imsize = 1024
                cell = ['2.5arcsec']
        if len(spwran) == 2:
            spwstr = spwran[0] + '~' + spwran[1]
        else:
            spwstr = spwran[0]

        restoringbeam = ['{0:.1f}arcsec'.format(bmsz)]
        imagesuffix = '.spw' + spwstr.replace('~', '-')
        # if cfreq > 10.:
        #     antenna = antenna + ';!0&1;!0&2'  # deselect the shortest baselines
        sto = stokes.replace(',', '')
        if c_external:
            cleanscript = os.path.join(imdir, 'ptclean_external.py')
            resfile = os.path.join(imdir, os.path.basename(msfile) + '.res.npz')
            os.system('rm -rf {}'.format(cleanscript))
            inpdict = {'vis': msfile, 'imageprefix': imdir, 'imagesuffix': imagesuffix, 'timerange': timerange,
                       'twidth': twidth, 'uvrange': uvrange,
                       'spw': spw, 'ncpu': ncpu, 'niter': 1000, 'gain': 0.05, 'antenna': antenna, 'imsize': imsize,
                       'cell': cell, 'stokes': sto, 'mask': mask, 'uvrange': uvrange,
                       'doreg': True, 'reftime': reftime, 'overwrite': overwrite, 'toTb': toTb,
                       'restoringbeam': restoringbeam,
                       'weighting': 'briggs', 'robust': robust,
                       'uvtaper': True, 'outertaper': ['30arcsec'], 'phasecenter': phasecenter}
            for key, val in inpdict.items():
                if type(val) is str:
                    inpdict[key] = '"{}"'.format(val)
            fi = open(cleanscript, 'wb')
            fi.write('from ptclean_cli import ptclean_cli as ptclean \n')
            fi.write('import numpy as np \n')
            ostrs = []
            for k, v in inpdict.iteritems():
                ostrs.append('{}={}'.format(k, v))
            ostr = ','.join(ostrs)
            fi.write('res = ptclean({}) \n'.format(ostr))
            # fi.write(
            #     'res = ptclean(vis={i[vis]},imageprefix={i[imageprefix]},imagesuffix={i[imagesuffix]},timerange={i[timerange]},twidth={i[twidth]},uvrange={i[uvrange]},spw={i[spw]},ncpu={i[ncpu]},niter={i[niter]},gain={i[gain]},antenna={i[antenna]},imsize={i[imsize]},cell={i[cell]},stokes={i[stokes]},doreg={i[doreg]},overwrite={i[overwrite]},toTb={i[toTb]},restoringbeam={i[restoringbeam]},uvtaper={i[uvtaper]},outertaper={i[outertaper]},phasecenter={i[phasecenter]}) \n'.format(
            #         i=inpdict))
            fi.write('np.savez("{}",res=res) \n'.format(resfile))
            fi.close()

            os.system('casa --nologger -c {}'.format(cleanscript))
            res = np.load(resfile)
            res = res['res'].item()
        else:
            res = ptclean(vis=msfile, imageprefix=imdir, imagesuffix=imagesuffix, timerange=timerange, twidth=twidth,
                          uvrange=uvrange, spw=spw, mask=mask,
                          ncpu=ncpu, niter=niter, gain=0.05, antenna=antenna, imsize=imsize, cell=cell, stokes=sto,
                          doreg=True, reftime=reftime, overwrite=overwrite,
                          toTb=toTb, restoringbeam=restoringbeam, weighting='briggs', robust=robust, uvtaper=True,
                          outertaper=['30arcsec'],
                          phasecenter=phasecenter)

        if res:
            imres['Succeeded'] += res['Succeeded']
            imres['BeginTime'] += res['BeginTime']
            imres['EndTime'] += res['EndTime']
            imres['ImageName'] += res['ImageName']
            imres['Spw'] += [spwstr] * len(res['ImageName'])
            imres['Vis'] += [msfile] * len(res['ImageName'])
            imres['Freq'] += [freqran] * len(res['ImageName'])
            imres['Obs'] += [observatory] * len(res['ImageName'])
        else:
            return None

    # save it for debugging purposes
    np.savez(os.path.join(imagedir, '{}.imres.npz'.format(os.path.basename(msfile))), imres=imres)

    return imres


def plt_qlook_image(imres, timerange='', figdir=None, specdata=None, verbose=True, stokes='I,V', fov=None, imax=None,
                    imin=None, dmax=None, dmin=None,
                    clevels=None, cmap='jet', aiafits=None, aiadir=None, aiawave=171, plotaia=True, moviename='',
                    alpha_cont=1.0, custom_mapcubes=[]):
    '''
    Required inputs:

    Important optional inputs:

    Optional inputs:
            aiadir: directory to search aia fits files
    Example:

    '''
    from matplotlib import pyplot as plt
    from sunpy import map as smap
    from sunpy import sun
    import astropy.units as u
    if not figdir:
        figdir = './'

    tstart, tend = timerange.split('~')
    tr = Time([qa.quantity(tstart, 'd')['value'], qa.quantity(tend, 'd')['value']], format='mjd')
    btimes = Time(imres['BeginTime'])
    etimes = Time(imres['EndTime'])
    tidx, = np.where(np.logical_and(btimes.jd >= tr[0].jd, etimes.jd <= tr[1].jd))
    # imres = imres['imres']
    if type(imres) is not dict:
        for k, v in imres.iteritems():
            imres[k] = list(np.array(v)[tidx])
    if 'Obs' in imres.keys():
        observatory = imres['Obs'][0]
    else:
        observatory = ''
    polmap = {'RR': 0, 'LL': 1, 'I': 0, 'V': 1, 'XX': 0, 'YY': 1}
    pols = stokes.split(',')
    npols = len(pols)
    # SRL = set(['RR', 'LL'])
    # SXY = set(['XX', 'YY', 'XY', 'YX'])
    Spw = sorted(list(set(imres['Spw'])))
    nspw = len(Spw)
    # Freq = set(imres['Freq']) ## list is an unhashable type
    imres['Freq'] = [list(ll) for ll in imres['Freq']]
    Freq = sorted(uniq(imres['Freq']))

    if custom_mapcubes:
        cmpc_plttimes_mjd = []
        for cmpc in custom_mapcubes['mapcube']:
            cmpc_plttimes_mjd.append(get_mapcube_time(cmpc).mjd)
    plttimes = list(set(imres['BeginTime']))
    ntime = len(plttimes)
    # sort the imres according to time
    images = np.array(imres['ImageName'])
    btimes = Time(imres['BeginTime'])
    etimes = Time(imres['EndTime'])
    spws = np.array(imres['Spw'])
    suc = np.array(imres['Succeeded'])
    inds = btimes.argsort()
    images_sort = images[inds].reshape(ntime, nspw)
    btimes_sort = btimes[inds].reshape(ntime, nspw)
    suc_sort = suc[inds].reshape(ntime, nspw)
    spws_sort = spws[inds].reshape(ntime, nspw)
    if verbose:
        print('{0:d} figures to plot'.format(ntime))
    plt.ioff()
    import matplotlib.gridspec as gridspec
    spec = specdata['spec']
    (npol, nbl, nfreq, ntim) = spec.shape
    # tidx = range(ntim)
    fidx = range(nfreq)
    tim = specdata['tim']
    freq = specdata['freq']
    freqghz = freq / 1e9
    pol = ''.join(pols)
    spec_tim = Time(specdata['tim'] / 3600. / 24., format='mjd')
    tidx, = np.where(np.logical_and(spec_tim > tr[0], spec_tim < tr[1]))
    spec_tim_plt = spec_tim.plot_date
    if npols == 1:
        if pol == 'RR':
            spec_plt = spec[0, 0, :, :]
        elif pol == 'LL':
            spec_plt = spec[1, 0, :, :]
        elif pol == 'XX':
            spec_plt = spec[0, 0, :, :]
        elif pol == 'YY':
            spec_plt = spec[1, 0, :, :]
        elif pol == 'I':
            spec_plt = (spec[0, 0, :, :] + spec[1, 0, :, :]) / 2.
        elif pol == 'V':
            spec_plt = (spec[0, 0, :, :] - spec[1, 0, :, :]) / 2.
        spec_plt = [spec_plt]
        print('plot the dynamic spectrum in pol ' + pol)

        hnspw = max(nspw / 2, 1)
        ncols = hnspw
        nrows = 2 + 2  # 1 image: 1x1, 1 dspec:2x4
        fig = plt.figure(figsize=(8, 8))
        gs = gridspec.GridSpec(nrows, ncols)
        if nspw > 1:
            axs = [plt.subplot(gs[:2, :hnspw])]
        else:
            axs = [plt.subplot(gs[0, 0])]
            for ll in range(1, nspw):
                axs.append(plt.subplot(gs[ll / hnspw, ll % hnspw], sharex=axs[0], sharey=axs[0]))
            for ll in range(nspw):
                axs.append(plt.subplot(gs[ll / hnspw + 2, ll % hnspw], sharex=axs[0], sharey=axs[0]))
        axs_dspec = [plt.subplot(gs[2:, :])]
        cmaps = ['jet']
    elif npols == 2:
        R_plot = np.absolute(spec[0, 0, :, :])
        L_plot = np.absolute(spec[1, 0, :, :])
        if pol == 'RRLL':
            spec_plt = [R_plot, L_plot]
            polstr = ['RR', 'LL']
            cmaps = ['jet'] * 2
        elif pol == 'XXYY':
            spec_plt = [R_plot, L_plot]
            polstr = ['XX', 'YY']
            cmaps = ['jet'] * 2
        elif pol == 'IV':
            I_plot = (R_plot + L_plot) / 2.
            V_plot = (R_plot - L_plot) / 2.
            spec_plt = [I_plot, V_plot]
            polstr = ['I', 'V']
            cmaps = ['jet', 'RdBu']
        print('plot the dynamic spectrum in pol ' + pol)

        hnspw = max(nspw / 2, 1)
        ncols = hnspw + 2  # 1 image: 1x1, 1 dspec:2x2
        nrows = 2 + 2
        fig = plt.figure(figsize=(12, 8))
        gs = gridspec.GridSpec(nrows, ncols)
        if nspw > 1:
            axs = [plt.subplot(gs[:2, 2:]), plt.subplot(gs[2:, 2:])]
        else:
            # pdb.set_trace()
            axs = [plt.subplot(gs[0, 2])]
            for ll in range(1, nspw):
                axs.append(plt.subplot(gs[ll / hnspw, ll % hnspw + 2], sharex=axs[0], sharey=axs[0]))
            for ll in range(nspw):
                axs.append(plt.subplot(gs[ll / hnspw + 2, ll % hnspw + 2], sharex=axs[0], sharey=axs[0]))

        axs_dspec = [plt.subplot(gs[:2, :2])]
        axs_dspec.append(plt.subplot(gs[2:, :2]))

    # fig.subplots_adjust(left=0, bottom=0, right=1, top=1, wspace=0, hspace=0)
    # pdb.set_trace()
    if plotaia:
        '''check if aiafits files exist'''
        if aiadir:
            aiafiles = []
            for i in range(ntime):
                plttime = btimes_sort[i, 0]
                aiafile = DButil.readsdofile(datadir=aiadir_default, wavelength=aiawave, trange=plttime, isexists=True,
                                             timtol=12. / 3600. / 24)
                if not aiafile:
                    aiafile = DButil.readsdofileX(datadir=aiadir, wavelength=aiawave, trange=plttime, isexists=True,
                                                  timtol=12. / 3600. / 24)
                if not aiafile:
                    aiafile = DButil.readsdofileX(datadir='./', wavelength=aiawave, trange=plttime, isexists=True,
                                                  timtol=12. / 3600. / 24)
                aiafiles.append(aiafile)
            if np.count_nonzero(aiafiles) < ntime / 2.0:
                downloadAIAdata(trange=tr, wavelength=aiawave)
                aiadir = './'

    for i in range(ntime):
        plt.ioff()
        # plt.clf()
        for ax in axs:
            ax.cla()
        plttime = btimes_sort[i, 0]
        # tofd = plttime.mjd - np.fix(plttime.mjd)
        suci = suc_sort[i]
        # if tofd < 16. / 24. or sum(
        #         suci) < nspw - 2:  # if time of the day is before 16 UT (and 24 UT), skip plotting (because the old antennas are not tracking)
        #     continue
        # fig=plt.figure(figsize=(9,6))
        # fig.suptitle('EOVSA @ '+plttime.iso[:19])
        if verbose:
            print('Plotting image at: ', plttime.iso)

        if i == 0:
            dspecvspans = []
            for pol in range(npols):
                ax = axs_dspec[pol]
                im_spec = ax.pcolormesh(spec_tim_plt[tidx], freqghz, spec_plt[pol][:, tidx] / 1e4, cmap=cmaps[pol],
                                        vmax=dmax, vmin=dmin, rasterized=True)
                ax.set_xlim(spec_tim_plt[tidx[0]], spec_tim_plt[tidx[-1]])
                ax.set_ylim(freqghz[fidx[0]], freqghz[fidx[-1]])
                ax.set_ylabel('Frequency [GHz]')
                for idx, freq in enumerate(Freq):
                    if nspw <= 10:
                        ax.axhspan(freq[0], freq[1], linestyle='dotted', edgecolor='w', alpha=0.7, facecolor='none')
                        xtext, ytext = ax.transAxes.inverted().transform(
                            ax.transData.transform([spec_tim_plt[tidx[0]], np.mean(freq)]))
                        ax.text(xtext + 0.01, ytext, 'spw ' + Spw[idx], color='w', transform=ax.transAxes,
                                fontweight='bold', ha='left', va='center',
                                fontsize=8, alpha=0.5)
                ax.text(0.01, 0.98, 'Stokes ' + pols[pol], color='w', transform=ax.transAxes, fontweight='bold',
                        ha='left', va='top')
                dspecvspans.append(ax.axvspan(btimes[i].plot_date, etimes[i].plot_date, color='w', alpha=0.4))
                ax_pos = ax.get_position().extents
                x0, y0, x1, y1 = ax_pos
                h, v = x1 - x0, y1 - y0
                x0_new = x0 + 0.10 * h
                y0_new = y0 + 0.20 * v
                x1_new = x1 - 0.03 * h
                y1_new = y1 - 0.00 * v
                # ax.set_position(mpl.transforms.Bbox([[x0_new, y0_new], [x1_new, y1_new]]))
                if pol == npols - 1:
                    ax.xaxis_date()
                    ax.xaxis.set_major_formatter(DateFormatter("%H:%M:%S"))
                    ax.set_xlabel('Time [UT]', fontsize=9)
                    for xlabel in ax.get_xmajorticklabels():
                        xlabel.set_rotation(30)
                        xlabel.set_horizontalalignment("right")
                else:
                    ax_pos = ax.get_position().extents
                    ax_pos2 = axs_dspec[-1].get_position().extents
                    x0, y0, x1, y1 = ax_pos
                    h, v = x1 - x0, y1 - y0
                    x0_new = x0
                    y0_new = ax_pos2[-1]
                    x1_new = x1
                    y1_new = y0_new + v
                    # ax.set_position(mpl.transforms.Bbox([[x0_new, y0_new], [x1_new, y1_new]]))
                    ax.xaxis.set_visible(False)
                divider = make_axes_locatable(ax)
                cax_spec = divider.append_axes('right', size='3.0%', pad=0.05)
                cax_spec.tick_params(direction='in')
                clb_spec = plt.colorbar(im_spec, ax=ax, cax=cax_spec)
                clb_spec.set_label('Flux [sfu]')
        else:
            for pol in range(npols):
                xy = dspecvspans[pol].get_xy()
                xy[:, 0][np.array([0, 1, 4])] = btimes[i].plot_date
                xy[:, 0][np.array([2, 3])] = etimes[i].plot_date
                dspecvspans[pol].set_xy(xy)

        if plotaia:
            # pdb.set_trace()
            try:
                if aiadir:
                    aiafits = DButil.readsdofileX(datadir=aiadir, wavelength=aiawave, trange=plttime, isexists=True,
                                                  timtol=12. / 3600. / 24)
                    if not aiafits:
                        aiafits = DButil.readsdofile(datadir=aiadir_default, wavelength=aiawave, trange=plttime,
                                                     isexists=True,
                                                     timtol=12. / 3600. / 24)
                aiamap = smap.Map(aiafits)
                aiamap = DButil.normalize_aiamap(aiamap)
                data = aiamap.data
                data[data < 1.0] = 1.0
                aiamap = smap.Map(data, aiamap.meta)
            except:
                aiamap = None
                print('error in reading aiafits. Proceed without AIA')
        else:
            aiamap = None

        colors_spws = cm.get_cmap(cmap)(np.linspace(0, 1, nspw))
        for n in range(nspw):
            image = images_sort[i, n]
            for pol in range(npols):
                if suci[n]:
                    try:
                        rmap = smap.Map(image)
                    except:
                        continue
                    sz = rmap.data.shape
                    if len(sz) == 4:
                        data = rmap.data[min(polmap[pols[pol]], rmap.meta['naxis4'] - 1), 0, :, :].reshape(
                            (sz[2], sz[3]))
                    elif len(sz) == 3:
                        data = rmap.data[min(polmap[pols[pol]], rmap.meta['naxis4'] - 1), :, :].reshape(
                            (sz[2], sz[3]))
                    else:
                        data = rmap.data

                    data[np.isnan(data)] = 0.0
                    data = data / 1e4
                    rmap = smap.Map(data, rmap.meta)
                else:
                    # make an empty map
                    data = np.zeros((512, 512))
                    header = {"DATE-OBS": plttime.isot, "EXPTIME": 0., "CDELT1": 5., "NAXIS1": 512, "CRVAL1": 0.,
                              "CRPIX1": 257, "CUNIT1": "arcsec",
                              "CTYPE1": "HPLN-TAN", "CDELT2": 5., "NAXIS2": 512, "CRVAL2": 0., "CRPIX2": 257,
                              "CUNIT2": "arcsec",
                              "CTYPE2": "HPLT-TAN", "HGLT_OBS": sun.heliographic_solar_center(plttime)[1].value,
                              "HGLN_OBS": 0.,
                              "RSUN_OBS": sun.solar_semidiameter_angular_size(plttime).value,
                              "RSUN_REF": sun.constants.radius.value,
                              "DSUN_OBS": sun.sunearth_distance(plttime).to(u.meter).value, }
                    rmap = smap.Map(data, header)
                # resample the image for plotting
                if fov is not None:
                    fov = [np.array(ll) for ll in fov]
                    try:
                        pad = max(np.diff(fov[0])[0], np.diff(fov[1])[0])
                        rmap = rmap.submap((fov[0] + np.array([-1.0, 1.0]) * pad) * u.arcsec,
                                           (fov[1] + np.array([-1.0, 1.0]) * pad) * u.arcsec)
                    except:
                        pad = max(fov[1][0] - fov[0][0], fov[1][1] - fov[0][1])
                        bl = SkyCoord((fov[0][0] - pad) * u.arcsec, (fov[1][0] - pad) * u.arcsec,
                                      frame=rmap.coordinate_frame)
                        tr = SkyCoord((fov[0][1] + pad) * u.arcsec, (fov[1][1] + pad) * u.arcsec,
                                      frame=rmap.coordinate_frame)
                        rmap = rmap.submap(bl, tr)
                else:
                    dim = u.Quantity([256, 256], u.pixel)
                    rmap = rmap.resample(dim)

                ax = axs[pol]
                if aiamap:
                    if nspw > 1:
                        if n == 0:
                            aiamap_ = pmX.Sunmap(aiamap)
                            aiamap_.imshow(axes=ax, cmap='gray',
                                           norm=colors.LogNorm(vmin=1.0, vmax=np.nanmax(aiamap.data)))
                    else:
                        aiamap_ = pmX.Sunmap(aiamap)
                        aiamap_.imshow(axes=ax, vmin=1.0, cmap='gray',
                                       norm=colors.LogNorm(vmin=1.0, vmax=np.nanmax(aiamap.data)))
                    try:
                        clevels1 = np.linspace(imin, imax, 3)
                    except:
                        try:
                            clevels1 = np.array(clevels) * np.nanmax(rmap.data)
                        except:
                            clevels1 = np.linspace(0.5, 1.0, 2) * np.nanmax(rmap.data)
                    rmap_ = pmX.Sunmap(rmap)
                    if nspw > 1:
                        rmap_.contourf(axes=ax, levels=clevels1,
                                       colors=[colors_spws[n]] * len(clevels1),
                                       alpha=alpha_cont)
                    else:
                        rmap_.contour(axes=ax, levels=clevels1, cmap=cm.get_cmap(cmap))
                else:
                    rmap_.imshow(axes=ax, vmax=imax, vmin=imin)
                    rmap_.draw_limb(axes=ax)
                    rmap_.draw_grid(axes=ax)
                if custom_mapcubes:
                    for cmpcidx, cmpc in enumerate(custom_mapcubes['mapcube']):
                        dtcmpc = np.mean(np.diff(cmpc_plttimes_mjd[cmpcidx]))
                        timeline = cmpc_plttimes_mjd[cmpcidx] - Time(plttime).mjd
                        if np.min(np.abs(timeline)) <= dtcmpc:
                            if 'levels' in custom_mapcubes.keys():
                                levels = np.array(custom_mapcubes['levels'][cmpcidx])
                            else:
                                levels = np.linspace(0.2, 0.9, 3)
                            if 'color' in custom_mapcubes.keys():
                                color = custom_mapcubes['color'][cmpcidx]
                            else:
                                color = None
                            cmpidx = np.argmin(np.abs(timeline))
                            cmp = cmpc[cmpidx]
                            if 'label' in custom_mapcubes.keys():
                                label = custom_mapcubes['label'][cmpcidx]
                            else:
                                label = '-'.join(['{:.0f}'.format(ll) for ll in cmp.measurement.value]) + ' {}'.format(
                                    cmp.measurement.unit)
                            cmp_ = pmX.Sunmap(cmp)
                            cmp_.contour(axes=ax, levels=np.array(levels) * np.nanmax(cmp.data), colors=color)
                            ax.text(0.97, (len(custom_mapcubes['mapcube']) - cmpcidx - 1) * 0.06 + 0.03, label,
                                    horizontalalignment='right',
                                    verticalalignment='bottom', transform=ax.transAxes, color=color)
                ax.set_autoscale_on(True)
                if fov:
                    ax.set_xlim(fov[0])
                    ax.set_ylim(fov[1])
                else:
                    ax.set_xlim([-1220, 1220])
                    ax.set_ylim([-1220, 1220])
                if nspw > 1:
                    if nspw <= 10:
                        try:
                            ax.text(0.98, 0.01 + 0.05 * n,
                                    'Stokes {1} @ {0:.3f} GHz'.format(rmap.meta['crval3'] / 1e9, pols[pol]),
                                    color=cm.get_cmap(cmap)(float(n) / (nspw - 1)), transform=ax.transAxes,
                                    fontweight='bold', ha='right')
                        except:
                            ax.text(0.98, 0.01 + 0.05 * n, 'Stokes {1} @ {0:.3f} GHz'.format(0., pols[pol]),
                                    color=cm.get_cmap(cmap)(float(n) / (nspw - 1)), transform=ax.transAxes,
                                    fontweight='bold', ha='right')
                else:
                    try:
                        ax.text(0.98, 0.01, 'Stokes {1} @ {0:.3f} GHz'.format(rmap.meta['crval3'] / 1e9, pols[pol]),
                                color='w',
                                transform=ax.transAxes, fontweight='bold', ha='right')
                    except:
                        ax.text(0.98, 0.01, 'Stokes {1} @ {0:.3f} GHz'.format(0., pols[pol]), color='w',
                                transform=ax.transAxes, fontweight='bold',
                                ha='right')
                if pol == 0 and n == 0:
                    timetext = ax.text(0.99, 0.98, '', color='w', fontweight='bold', fontsize=9, ha='right', va='top',
                                       transform=ax.transAxes)
                timetext.set_text(plttime.iso[:19])
                ax.set_title(' ')
                ax.xaxis.set_visible(False)
                ax.yaxis.set_visible(False)
        if nspw > 10:
            for pol in range(npols):
                ax = axs[pol]
                divider = make_axes_locatable(ax)
                cax_freq = divider.append_axes('right', size='3.0%', pad=0.05)
                cax_freq.tick_params(direction='in')
                Freqs = [np.mean(fq) for fq in Freq]
                mpl.colorbar.ColorbarBase(cax_freq, cmap=cmap, norm=colors.Normalize(vmax=Freqs[-1], vmin=Freqs[0]))
                cax_freq.set_ylabel('Frequency [GHz]')
        figname = observatory + '_qlimg_' + plttime.isot.replace(':', '').replace('-', '')[:19] + '.png'
        # fig_tdt = plttime.to_datetime())
        # fig_subdir = fig_tdt.strftime("%Y/%m/%d/")
        figdir_ = figdir + '/'  # + fig_subdir
        if not os.path.exists(figdir_):
            os.makedirs(figdir_)
        if verbose:
            print('Saving plot to: ' + os.path.join(figdir_, figname))
        plt.savefig(os.path.join(figdir_, figname))
    plt.close(fig)
    if not moviename:
        moviename = 'movie'
    DButil.img2html_movie(figdir_, outname=moviename)


def dspec_external(vis, workdir='./', specfile=None):
    dspecscript = os.path.join(workdir, 'dspec.py')
    if not specfile:
        specfile = os.path.join(workdir, os.path.basename(vis) + '.dspec.npz')
    os.system('rm -rf {}'.format(dspecscript))
    fi = open(dspecscript, 'wb')
    fi.write('from suncasa.utils import dspec as ds \n')
    fi.write('specdata = ds.get_dspec("{0}", specfile="{1}", domedian=True, verbose=True, savespec=True) \n'.format(vis,
                                                                                                                    specfile))
    fi.close()
    os.system('casa --nologger -c {}'.format(dspecscript))


def qlookplot(vis, timerange=None, spw='', workdir='./', specfile=None, bl=None, uvrange='', stokes='RR,LL', dmin=None,
              dmax=None, goestime=None,
              reftime='', xycen=None, fov=[500., 500.], xyrange=None, restoringbeam=[''], robust=0.0, niter=500,
              imsize=[512], cell=['5.0arcsec'], mask='',
              interactive=False, usemsphacenter=True, imagefile=None, outfits='', plotaia=True, aiawave=171,
              aiafits=None, aiadir=None, savefig=False,
              mkmovie=False, overwrite=True, ncpu=10, twidth=1, verbose=False, imax=None, imin=None,
              clearmshistory=False, clevels=None, calpha=0.5):
    '''
    Required inputs:
            vis: calibrated CASA measurement set
    Important optional inputs:
            timerange: timerange for clean. Standard CASA time selection format.
                       If not provided, use the entire range (*BE CAREFUL, COULD BE VERY SLOW*)
            spw: spectral window selection following the CASA syntax.
                 Examples: spw='1:2~60' (spw id 1, channel range 2-60); spw='*:1.2~1.3GHz' (selects all channels within 1.2-1.3 GHz; note the *)
                 spw can be a list of spectral windows, i.e, ['0', '1', '2', '3', '4', '5', '6', '7']
            specfile: supply dynamic spectrum save file (from suncasa.utils.dspec.get_dspec()). Otherwise
                      generate a median dynamic spectrum on the fly
    Optional inputs:
            bl: baseline to generate dynamic spectrum
            uvrange: uvrange to select baselines for generating dynamic spectrum
            stokes: polarization of the clean image, can be 'RR,LL' or 'I,V'
            dmin,dmax: color bar parameter
            goestime: goes plot time, example ['2016/02/18 18:00:00','2016/02/18 23:00:00']
            rhessisav: rhessi savefile
            reftime: reftime for the image
            xycen: center of the image in helioprojective coordinates (HPLN/HPLT), in arcseconds. Example: [900, -150.]
            mask: only accept CASA region format (https://casaguides.nrao.edu/index.php/CASA_Region_Format)
            fov: field of view in arcsecs. Example: [500., 500.]
            xyrange: field of view in solar XY coordinates. Format: [[x1,x2],[y1,y2]]. Example: [[900., 1200.],[0,300]]
                     ***NOTE: THIS PARAMETER OVERWRITES XYCEN AND FOV***
            aiawave: wave length of aia file in a
            imagefile: if imagefile provided, use it. Otherwise do clean and generate a new one.
            outfits: if outfits provided, use it. Otherwise generate a new one
            savefig: whether to save the figure
            imax/imin: maximum/minimum value for radio image scaling
            clevels: clevels for the contours
    Example:

    '''

    if aiadir == None:
        aiadir = './'
    if xycen:
        xc, yc = xycen
        if len(fov) == 1:
            fov = fov * 2
        xlen, ylen = fov
        # if parse_version(sunpy.__version__) > parse_version('0.8.0'):
        #     xyrange = [[xc - xlen / 2.0, yc - ylen / 2.0], [xc + xlen / 2.0, yc + ylen / 2.0]]
        # else:
        xyrange = [[xc - xlen / 2.0, xc + xlen / 2.0], [yc - ylen / 2.0, yc + ylen / 2.0]]
    stokes_allowed = ['RR,LL', 'I,V', 'RRLL', 'IV', 'XXYY', 'XX,YY', 'RR', 'LL', 'I', 'V', 'XX', 'YY']
    if not stokes in stokes_allowed:
        print('wrong stokes parameter ' + str(stokes) + '. Allowed values are ' + ';  '.join(stokes_allowed))
        return -1
    if stokes == 'RRLL':
        stokes = 'RR,LL'
    elif stokes == 'XXYY':
        stokes = 'XX,YY'
    elif stokes == 'IV':
        stokes = 'I,V'

    polmap = {'RR': 0, 'LL': 1, 'I': 0, 'V': 1, 'XX': 0, 'YY': 1}
    pols = stokes.split(',')
    npol_in = len(pols)

    if vis[-1] == '/':
        vis = vis[:-1]
    if not os.path.exists(vis):
        print('input measurement not exist')
        return -1
    if clearmshistory:
        msclearhistory(vis)
    if aiafits is None:
        aiafits = ''
    # split the data
    # generating dynamic spectrum
    if not os.path.exists(workdir):
        os.makedirs(workdir)
    if specfile:
        try:
            specdata = np.load(specfile)
        except:
            print('Provided dynamic spectrum file not numpy npz. Generating one from the visibility data')
            specfile = os.path.join(workdir, os.path.basename(vis) + '.dspec.npz')
            dspec_external(vis, workdir=workdir, specfile=specfile)
            specdata = np.load(specfile)  # specdata = ds.get_dspec(vis, domedian=True, verbose=True)
    else:
        print('Dynamic spectrum file not provided; Generating one from the visibility data')
        # specdata = ds.get_dspec(vis, domedian=True, verbose=True)
        specfile = os.path.join(workdir, os.path.basename(vis) + '.dspec.npz')
        dspec_external(vis, workdir=workdir, specfile=specfile)
        specdata = np.load(specfile)

    # tb.open(vis)
    # starttim = Time(tb.getcell('TIME', 0) / 24. / 3600., format='mjd')
    # endtim = Time(tb.getcell('TIME', tb.nrows() - 1) / 24. / 3600., format='mjd')
    tb.open(vis + '/POINTING')
    starttim = Time(tb.getcell('TIME_ORIGIN', 0) / 24. / 3600., format='mjd')
    endtim = Time(tb.getcell('TIME_ORIGIN', tb.nrows() - 1) / 24. / 3600., format='mjd')
    tb.close()
    datstr = starttim.iso[:10]

    if timerange is None or timerange == '':
        starttim1 = starttim
        endtim1 = endtim
        timerange = '{0}~{1}'.format(starttim.iso.replace('-', '/').replace(' ', '/'),
                                     endtim.iso.replace('-', '/').replace(' ', '/'))
    else:
        try:
            (tstart, tend) = timerange.split('~')
            if tstart[2] == ':':
                starttim1 = Time(datstr + 'T' + tstart)
                endtim1 = Time(datstr + 'T' + tend)
                timerange = '{0}/{1}~{0}/{2}'.format(datstr.replace('-', '/'), tstart, tend)
            else:
                starttim1 = Time(qa.quantity(tstart, 'd')['value'], format='mjd')
                endtim1 = Time(qa.quantity(tend, 'd')['value'], format='mjd')
        except ValueError:
            print("keyword 'timerange' in wrong format")
    midtime_mjd = (starttim1.mjd + endtim1.mjd) / 2.

    if vis.endswith('/'):
        vis = vis[:-1]
    visname = os.path.basename(vis)
    bt = starttim1.plot_date
    et = endtim1.plot_date

    # find out min and max frequency for plotting in dynamic spectrum
    ms.open(vis)
    metadata = ms.metadata()
    observatory = metadata.observatorynames()[0]
    spwInfo = ms.getspectralwindowinfo()
    nspw = len(spwInfo)
    if not spw:
        if observatory == 'EOVSA':
            if nspw == 31:
                spw = list((np.arange(30) + 1).astype(str))
                spwselec = '1~' + str(30)
                spw = [str(sp) for sp in spw]
            else:
                spw = list(np.arange(nspw).astype(str))
                spwselec = '0~' + str(nspw - 1)
                spw = [str(sp) for sp in spw]
        else:
            spwselec = '0~' + str(nspw - 1)
            spw = [spwselec]
    else:
        if type(spw) is list:
            spwselec = ';'.join(spw)
        else:
            spwselec = spw
            spw = [spw]  # spw=spw.split(';')

    staql = {'timerange': timerange, 'spw': spwselec}
    if ms.msselect(staql, onlyparse=True):
        ndx = ms.msselectedindices()
        chan_sel = ndx['channel']
        bspw = chan_sel[0, 0]
        bchan = chan_sel[0, 1]
        espw = chan_sel[-1, 0]
        echan = chan_sel[-1, 2]
        bfreq = spwInfo[str(bspw)]['Chan1Freq'] + spwInfo[str(bspw)]['ChanWidth'] * bchan
        efreq = spwInfo[str(espw)]['Chan1Freq'] + spwInfo[str(espw)]['ChanWidth'] * echan
        bfreqghz = bfreq / 1e9
        efreqghz = efreq / 1e9
        if verbose:
            print('selected timerange {}'.format(timerange))
            print('selected frequency range {0:6.3f} to {1:6.3f} GHz'.format(bfreqghz, efreqghz))
    else:
        print("spw or timerange selection failed. Aborting...")
        ms.close()
        return -1
    ms.close()

    nspws = len(spw)
    if observatory == 'EOVSA':
        if stokes == 'RRLL' or stokes == 'RR,LL':
            print('Provide stokes: ' + str(stokes) + '. However EOVSA has linear feeds. Force stokes to be XXYY')
            stokes = 'XX,YY'

    if mkmovie:
        plt.ioff()
        # fig = plt.figure(figsize=(12, 7.5), dpi=100)
        if outfits:
            pass
        else:
            eph = hf.read_horizons(t0=Time(midtime_mjd, format='mjd'))
            if observatory == 'EOVSA' or (not usemsphacenter):
                print('This is EOVSA data')
                # use RA and DEC from FIELD ID 0
                tb.open(vis + '/FIELD')
                phadir = tb.getcol('PHASE_DIR').flatten()
                tb.close()
                ra0 = phadir[0]
                dec0 = phadir[1]
                if stokes == 'RRLL' or stokes == 'RR,LL':
                    print('Provide stokes: ' + str(
                        stokes) + '. However EOVSA has linear feeds. Force stokes to be XX,YY')
                    stokes = 'XX,YY'
            else:
                ra0 = eph['ra'][0]
                dec0 = eph['dec'][0]

            if not xycen:
                # use solar disk center as default
                phasecenter = 'J2000 ' + str(ra0) + 'rad ' + str(dec0) + 'rad'
            else:
                x0 = np.radians(xycen[0] / 3600.)
                y0 = np.radians(xycen[1] / 3600.)
                p0 = np.radians(eph['p0'][0])  # p angle in radians
                raoff = -((x0) * np.cos(p0) - y0 * np.sin(p0)) / np.cos(eph['dec'][0])
                decoff = (x0) * np.sin(p0) + y0 * np.cos(p0)
                newra = ra0 + raoff
                newdec = dec0 + decoff
                phasecenter = 'J2000 ' + str(newra) + 'rad ' + str(newdec) + 'rad'
            print('use phasecenter: ' + phasecenter)
            qlookfitsdir = os.path.join(workdir, 'qlookfits/')
            qlookfigdir = os.path.join(workdir, 'qlookimgs/')
            imresfile = os.path.join(qlookfitsdir, '{}.imres.npz'.format(os.path.basename(vis)))
            if overwrite:
                imres = mk_qlook_image(vis, timerange=timerange, spws=spw, twidth=twidth, ncpu=ncpu,
                                       imagedir=qlookfitsdir, phasecenter=phasecenter, stokes=stokes, mask=mask,
                                       uvrange=uvrange, robust=robust, niter=niter, imsize=imsize, cell=cell,
                                       reftime=reftime, c_external=True)
            else:
                if os.path.exists(imresfile):
                    imres = np.load(imresfile)
                    imres = imres['imres'].item()
                else:
                    print('Image results file not found; Creating new images.')
                    imres = mk_qlook_image(vis, timerange=timerange, spws=spw, twidth=twidth, ncpu=ncpu,
                                           imagedir=qlookfitsdir, phasecenter=phasecenter, stokes=stokes, mask=mask,
                                           uvrange=uvrange, robust=robust, niter=niter, imsize=imsize, cell=cell,
                                           reftime=reftime, c_external=True)
            if not os.path.exists(qlookfigdir):
                os.makedirs(qlookfigdir)
            plt_qlook_image(imres, timerange=timerange, figdir=qlookfigdir, specdata=specdata, verbose=True,
                            stokes=stokes, fov=xyrange, imax=imax, imin=imin, dmax=dmax, dmin=dmin, aiafits=aiafits,
                            aiawave=aiawave, aiadir=aiadir, plotaia=plotaia, alpha_cont=calpha)

    else:
        cfreqs = []
        spec = specdata['spec']
        (npol_fits, nbl, nfreq, ntim) = spec.shape
        fidx = range(nfreq)
        tim = specdata['tim']
        freq = specdata['freq']
        freqghz = freq / 1e9
        spec_tim = Time(specdata['tim'] / 3600. / 24., format='mjd')
        spec_tim_plt = spec_tim.plot_date
        plt.ion()
        # fig = plt.figure(figsize=(11.65, 8.74), dpi=100)
        fig = plt.figure(figsize=(11.80, 8.80), dpi=100)
        ax1 = plt.subplot2grid((6, 8), (0, 0), rowspan=2, colspan=2)
        ax2 = plt.subplot2grid((6, 8), (2, 0), rowspan=2, colspan=2, sharex=ax1, sharey=ax1)
        ax3 = plt.subplot2grid((6, 8), (4, 0), rowspan=2, colspan=2)
        ax4 = plt.subplot2grid((6, 8), (0, 2), rowspan=3, colspan=3)
        ax5 = plt.subplot2grid((6, 8), (3, 2), rowspan=3, colspan=3)
        ax6 = plt.subplot2grid((6, 8), (0, 5), rowspan=3, colspan=3, sharex=ax4, sharey=ax4)
        ax7 = plt.subplot2grid((6, 8), (3, 5), rowspan=3, colspan=3, sharex=ax5, sharey=ax5)

        specs = {}
        if npol_in > 1:
            if npol_fits > 1:
                specs[pols[0]] = np.absolute(spec[0, 0, :, :])
                specs[pols[1]] = np.absolute(spec[1, 0, :, :])
            else:
                warnings.warn(
                    "The provided specfile only provides one polarization. The polarization of the dynamic spectrum could be wrong.")
                specs[pols[0]] = np.absolute(spec[0, 0, :, :])
                specs[pols[1]] = np.zeros_like(spec[0, 0, :, :])
        else:
            if npol_fits > 1:
                specs[pols[0]] = np.absolute(spec[polmap[pols[0]], 0, :, :])
            else:
                specs[pols[0]] = np.absolute(spec[0, 0, :, :])

        print('plot the dynamic spectrum in pol ' + ' & '.join(pols))

        axs = [ax1, ax2]
        for axidx, ax in enumerate(axs):
            if axidx < npol_in:
                ax.pcolormesh(spec_tim_plt, freqghz, specs[pols[axidx]], cmap='jet', vmin=dmin, vmax=dmax,
                              rasterized=True)
                ax.set_title(observatory + ' ' + datstr + ' ' + pols[axidx], fontsize=9)
            ax.set_autoscale_on(True)
            ax.add_patch(patches.Rectangle((bt, bfreqghz), et - bt, efreqghz - bfreqghz, ec='w', fill=False))
            ax.plot([(bt + et) / 2.], [(bfreqghz + efreqghz) / 2.], '*w', ms=12)
            for tick in ax.get_xticklabels():
                tick.set_rotation(30)
                tick.set_fontsize(8)
            ax.set_ylabel('Frequency (GHz)', fontsize=9)
            if axidx == 1:
                ax.xaxis_date()
                ax.xaxis.set_major_formatter(DateFormatter("%H:%M:%S"))
                locator = mpl.dates.AutoDateLocator()
                ax.xaxis.set_major_locator(locator)
                ax.set_xlim(spec_tim_plt[0], spec_tim_plt[-1])
                ax.set_ylim(freqghz[0], freqghz[-1])

        # import pdb
        # pdb.set_trace()
        # Second part: GOES plot
        if goestime:
            btgoes = goestime[0]
            etgoes = goestime[1]
        else:
            # datstrg = datstr.replace('-', '/')
            tdur = np.nanmax([tim[-1] - tim[0], 1200])
            btgoes = datstr + ' ' + qa.time(qa.quantity(tim[0] - tdur, 's'), form='clean', prec=9)[0]
            etgoes = datstr + ' ' + qa.time(qa.quantity(tim[-1] + tdur, 's'), form='clean', prec=9)[0]
        if verbose:
            print('Acquire GOES soft X-ray data in from ' + btgoes + ' to ' + etgoes)

        # ax3 = plt.subplot(gs1[2])

        from sunpy.timeseries import TimeSeries
        from sunpy.time import TimeRange, parse_time
        from sunpy.net import Fido, attrs as a
        btgoes = btgoes.replace('/', '-')
        etgoes = etgoes.replace('/', '-')
        results = Fido.search(a.Time(TimeRange(btgoes, etgoes)), a.Instrument('XRS'))
        files = Fido.fetch(results)
        goest = TimeSeries(files)
        dates = mpl.dates.date2num(parse_time(goest.data.index))

        try:
            if np.abs(goest.data['xrsb'].mean()) > 1e-9:
                goesdata = goest.data['xrsb']
                goesdif = np.diff(goest.data['xrsb'])
            else:
                dates, goesdata = get_goes_data(Time((tim[-1] + tim[0]) / 3600. / 24. / 2.0, format='mjd'))
                goesdif = np.diff(goesdata)

            gmax = np.nanmax(goesdif)
            gmin = np.nanmin(goesdif)
            ran = gmax - gmin
            db = 2.8 / ran
            goesdifp = goesdif * db + gmin + (-6)
            ax3.step(dates, np.log10(goesdata), '-', label='1.0--8.0 $\AA$', color='red', lw=1.0)
            ax3.step(dates[0:-1], goesdifp, '-', label='Derivative', color='blue', lw=0.5)

            ax3.set_ylim([-8, -3])
            ax3.set_yticks([-8, -7, -6, -5, -4, -3])
            ax3.set_yticklabels([r'$10^{-8}$', r'$10^{-7}$', r'$10^{-6}$', r'$10^{-5}$', r'$10^{-4}$', r'$10^{-3}$'])
            ax3.set_title('Goes Soft X-ray', fontsize=9)
            ax3.set_ylabel('Watts m$^{-2}$')
            ax3.set_xlabel(Time(spec_tim_plt[0], format='plot_date').iso[0:10])
            ax3.axvspan(spec_tim_plt[0], spec_tim_plt[-1], alpha=0.2)
            ax3.set_xlim(Time([btgoes, etgoes]).plot_date)

            for tick in ax3.get_xticklabels():
                tick.set_fontsize(8)
                tick.set_rotation(30)

            ax3_2 = ax3.twinx()
            # ax3_2.set_yscale("log")
            ax3_2.set_ylim([-8, -3])
            ax3_2.set_yticks([-8, -7, -6, -5, -4, -3])
            ax3_2.set_yticklabels(['A', 'B', 'C', 'M', 'X', ''])

            ax3.yaxis.grid(True, 'major')
            ax3.xaxis.grid(False, 'major')
            ax3.legend(prop={'size': 6})

            formatter = mpl.dates.DateFormatter('%H:%M')
            ax3.xaxis.set_major_formatter(formatter)
            locator = mpl.dates.AutoDateLocator()
            ax3.xaxis.set_major_locator(locator)

            ax3.fmt_xdata = mpl.dates.DateFormatter('%H:%M')
        except:
            print('Error in downloading GOES soft X-ray data. Proceeding with out soft X-ray plot.')

        # third part
        # start to download the fits files
        if plotaia:
            cmap_aia = cm_sunpy.get_cmap('sdoaia{}'.format(aiawave))
            if not aiafits:
                try:
                    newlist = trange2aiafits(Time([starttim1, endtim1]), aiawave, aiadir)
                except:
                    newlist = [-1]
            else:
                newlist = [aiafits]

            try:
                aiafits = newlist[0]
                aiamap = smap.Map(aiafits)
                aiamap = DButil.normalize_aiamap(aiamap)
                data = aiamap.data
                data[data < 1.0] = 1.0
                aiamap = smap.Map(data, aiamap.meta)
            except:
                print('error in reading aiafits. Proceed without AIA')

        if (os.path.exists(outfits)) and (not overwrite):
            pass
        else:
            if not imagefile:
                eph = hf.read_horizons(t0=Time(midtime_mjd, format='mjd'))
                if observatory == 'EOVSA' or (not usemsphacenter):
                    print('This is EOVSA data')
                    # use RA and DEC from FIELD ID 0
                    tb.open(vis + '/FIELD')
                    phadir = tb.getcol('PHASE_DIR').flatten()
                    tb.close()
                    ra0 = phadir[0]
                    dec0 = phadir[1]
                    if stokes == 'RRLL' or stokes == 'RR,LL':
                        print('Provide stokes: ' + str(
                            stokes) + '. However EOVSA has linear feeds. Force stokes to be IV')
                        stokes = 'I,V'
                else:
                    ra0 = eph['ra'][0]
                    dec0 = eph['dec'][0]

                if not xycen:
                    # use solar disk center as default
                    phasecenter = 'J2000 ' + str(ra0) + 'rad ' + str(dec0) + 'rad'
                else:
                    x0 = np.radians(xycen[0] / 3600.)
                    y0 = np.radians(xycen[1] / 3600.)
                    p0 = np.radians(eph['p0'][0])  # p angle in radians
                    raoff = -((x0) * np.cos(p0) - y0 * np.sin(p0)) / np.cos(eph['dec'][0])
                    decoff = (x0) * np.sin(p0) + y0 * np.cos(p0)
                    newra = ra0 + raoff
                    newdec = dec0 + decoff
                    phasecenter = 'J2000 ' + str(newra) + 'rad ' + str(newdec) + 'rad'

                if nspws > 1:
                    imagefiles, fitsfiles = [], []
                    if restoringbeam == ['']:
                        restoringbm = ['']
                    else:
                        tb.open(vis + '/SPECTRAL_WINDOW')
                        reffreqs = tb.getcol('REF_FREQUENCY')
                        bdwds = tb.getcol('TOTAL_BANDWIDTH')
                        cfreqs = reffreqs + bdwds / 2.
                        tb.close()
                        sbeam = 35.
                    for sp in spw:
                        if not restoringbeam == ['']:
                            try:
                                cfreq = cfreqs[int(sp)]
                                restoringbm = [str(max(sbeam * cfreqs[1] / cfreq, 10.)) + 'arcsec']
                            except:
                                restoringbm = restoringbeam
                        spwran = [s.zfill(2) for s in sp.split('~')]
                        if len(spwran) == 2:
                            spstr = spwran[0] + '~' + spwran[1]
                        else:
                            spstr = spwran[0]
                        imagename = os.path.join(workdir, visname + '_s' + spstr + '.outim')
                        junks = ['.image', '.image.pbcor', '.flux']
                        for junk in junks:
                            if os.path.exists(imagename + junk):
                                os.system('rm -rf ' + imagename + junk + '*')
                        sto = stokes.replace(',', '')

                        print('do clean for ' + timerange + ' in spw ' + sp + ' stokes ' + sto)
                        print('Original phasecenter: ' + str(ra0) + str(dec0))
                        print('use phasecenter: ' + phasecenter)
                        print('use beamsize {}'.format(restoringbm))
                        tclean(vis=vis,
                               imagename=imagename,
                               selectdata=True,
                               spw=sp,
                               timerange=timerange,
                               stokes=sto,
                               niter=niter,
                               interactive=interactive,
                               mask=mask,
                               uvrange=uvrange,
                               pbcor=True,
                               imsize=imsize,
                               cell=cell,
                               restoringbeam=restoringbm,
                               weighting='briggs',
                               robust=robust,
                               phasecenter=phasecenter)

                        junks = ['.flux', '.model', '.psf', '.residual', '.mask', '.image', '.pb', '.sumwt']
                        for junk in junks:
                            if os.path.exists(imagename + junk):
                                os.system('rm -rf ' + imagename + junk)
                        imagefile = imagename + '.image.pbcor'
                        ofits = imagefile + '.fits'
                        imagefiles.append(imagefile)
                        fitsfiles.append(ofits)
                    hf.imreg(vis=vis, imagefile=imagefiles, timerange=[timerange] * len(imagefiles), reftime=reftime,
                             fitsfile=fitsfiles,
                             verbose=verbose, overwrite=True, scl100=True, toTb=True)
                    print('fits file ' + ','.join(fitsfiles) + ' selected')
                    from suncasa.utils import fits_wrap as fw
                    if not outfits:
                        outfits = visname + '.outim.image.fits'
                    fw.fits_wrap_spwX(fitsfiles, outfitsfile=outfits)
                    warnings.warn(
                        "If the provided spw is not equally spaced, the frequency information of the fits file {} that combining {} could be a wrong. Use it with caution!".format(
                            outfits, ','.join(fitsfiles)))

                else:
                    imagename = os.path.join(workdir, visname + '.outim')
                    junks = ['.image', '.image.pbcor', '.flux']
                    for junk in junks:
                        if os.path.exists(imagename + junk):
                            os.system('rm -rf ' + imagename + junk + '*')
                    sto = stokes.replace(',', '')
                    print('do clean for ' + timerange + ' in spw ' + ';'.join(spw) + ' stokes ' + sto)
                    print('Original phasecenter: ' + str(ra0) + str(dec0))
                    print('use phasecenter: ' + phasecenter)

                    tclean(vis=vis,
                           imagename=imagename,
                           selectdata=True,
                           spw=';'.join(spw),
                           timerange=timerange,
                           stokes=sto,
                           niter=niter,
                           interactive=interactive,
                           mask=mask,
                           uvrange=uvrange,
                           pbcor=True,
                           imsize=imsize,
                           cell=cell,
                           restoringbeam=restoringbeam,
                           weighting='briggs',
                           robust=robust,
                           phasecenter=phasecenter)

                    junks = ['.flux', '.model', '.psf', '.residual', '.mask', '.image', '.pb', '.sumwt']
                    for junk in junks:
                        if os.path.exists(imagename + junk):
                            os.system('rm -rf ' + imagename + junk)
                    imagefile = imagename + '.image.pbcor'
                    if not outfits:
                        outfits = imagefile + '.fits'
                    hf.imreg(vis=vis, imagefile=imagefile, timerange=timerange, reftime=reftime,
                             fitsfile=outfits,
                             verbose=verbose, overwrite=True, scl100=True, toTb=True)
                    print('fits file ' + outfits + ' selected')
            else:
                if not outfits:
                    outfits = imagefile + '.fits'
                hf.imreg(vis=vis, imagefile=imagefile, timerange=timerange, reftime=reftime,
                         fitsfile=outfits,
                         verbose=verbose, overwrite=True, scl100=True, toTb=True)
                print('fits file ' + outfits + ' selected')
        ax4.cla()
        ax5.cla()
        ax6.cla()
        ax7.cla()

        rfits = outfits
        # if nspws>1:
        #     pass
        # else:
        try:
            if isinstance(rfits, list):
                hdulist = fits.open(rfits[0])
            else:
                hdulist = fits.open(rfits)
            hdu = hdulist[0]
            (npol_fits, nf, ny, nx) = hdu.data.shape
            hdu.data[np.isnan(hdu.data)] = 0.0
            rmap = smap.Map(hdu.data[0, 0, :, :], hdu.header)
            cfreqs = (hdu.header['CRVAL3'] + hdu.header['CDELT3'] * np.arange(hdu.header['NAXIS3'])) / 1e9
        except:
            print('radio fits file not recognized by sunpy.map. Aborting...')
            return -1

        if npol_fits != npol_in:
            warnings.warn("The input stokes setting is not matching those in the provided fitsfile.")
        datas = {}
        cmaps = {}
        cmap_I = plt.cm.jet
        cmap_V = plt.cm.RdBu
        if npol_in > 1:
            if npol_fits > 1:
                if stokes == 'I,V':
                    datas['I'] = (hdu.data[0, :, :, :] + hdu.data[1, :, :, :]) / 2.0
                    datas['V'] = (hdu.data[0, :, :, :] - hdu.data[1, :, :, :]) / 2.0
                    cmaps['I'] = cmap_I
                    cmaps['V'] = cmap_V
                else:
                    datas[pols[0]] = hdu.data[polmap[pols[0]], :, :, :]
                    datas[pols[1]] = hdu.data[polmap[pols[1]], :, :, :]
                    cmaps[pols[0]] = cmap_I
                    cmaps[pols[1]] = cmap_I
            else:
                datas[pols[0]] = hdu.data[0, :, :, :]
                cmaps[pols[0]] = cmap_I
        else:
            if npol_fits > 1:
                if pols[0] in ['I', 'V']:
                    if pols[0] == 'I':
                        datas['I'] = (hdu.data[0, :, :, :] + hdu.data[1, :, :, :]) / 2.0
                        cmaps['I'] = cmap_I
                    else:
                        datas['V'] = (hdu.data[0, :, :, :] - hdu.data[1, :, :, :]) / 2.0
                        cmaps['V'] = cmap_V
                else:
                    datas[pols[0]] = hdu.data[polmap[pols[0]], :, :, :]
                    cmaps[pols[0]] = cmap_I
            else:
                datas[pols[0]] = hdu.data[0, :, :, :]
                cmaps[pols[0]] = cmap_I

        if not xyrange:
            if xycen:
                x0 = xycen[0] * u.arcsec
                y0 = xycen[1] * u.arcsec
            if not xycen:
                row, col = rmap.data.shape
                positon = np.nanargmax(rmap.data)
                m, n = divmod(positon, col)
                x0 = rmap.xrange[0] + rmap.scale[1] * (n + 0.5) * u.pix
                y0 = rmap.yrange[0] + rmap.scale[0] * (m + 0.5) * u.pix
            if len(fov) == 1:
                fov = [fov] * 2
            sz_x = fov[0] * u.arcsec
            sz_y = fov[1] * u.arcsec
            x1 = x0 - sz_x / 2.
            x2 = x0 + sz_x / 2.
            y1 = y0 - sz_y / 2.
            y2 = y0 + sz_y / 2.
            xyrange = [[x1.to(u.arcsec).value, x2.to(u.arcsec).value], [y1.to(u.arcsec).value, y2.to(u.arcsec).value]]
        else:
            sz_x = (xyrange[0][1] - xyrange[0][0]) * u.arcsec
            sz_y = (xyrange[1][1] - xyrange[1][0]) * u.arcsec

        clvls = {}
        if nspws < 2:
            for pol in pols:
                if pol == 'V':
                    clvls[pol] = np.array([0.8, -0.6, -0.4, -0.2, 0.2, 0.4, 0.6, 0.8])
                else:
                    if clevels is None:
                        clvls[pol] = np.linspace(0.2, 0.9, 5)
                    else:
                        clvls[pol] = np.array(clevels)
        else:
            for pol in pols:
                if pol == 'V':
                    clvls[pol] = np.array([0.8, -0.6, -0.4, -0.2, 0.2, 0.4, 0.6, 0.8])
                else:
                    if clevels is None:
                        clvls[pol] = np.linspace(0.3, 1, 2)
                    else:
                        clvls[pol] = np.array(clevels)

        if 'aiamap' in vars():
            title0 = 'AIA {0:.0f}'.format(aiamap.wavelength.value)
            aiamap_ = pmX.Sunmap(aiamap)

            axs = [ax4, ax6]
            aiamap_.draw_limb(axes=axs)
            aiamap_.draw_grid(axes=axs)
            aiamap_.imshow(axes=axs, cmap=cmap_aia, norm=colors.LogNorm(vmin=1.0))
            for axidx, ax in enumerate(axs):
                ax.set_title(title0, fontsize=9)
                rect = mpl.patches.Rectangle((xyrange[0][0], xyrange[1][0]), sz_x.value, sz_y.value, edgecolor='w',
                                             facecolor='none')
                ax.add_patch(rect)

            axs = [ax5, ax7]
            aiamap_.draw_limb(axes=axs)
            aiamap_.draw_grid(axes=axs)
            aiamap_.imshow(axes=axs, cmap=cmap_aia, norm=colors.LogNorm(vmin=1.0))

            axs = [[ax4, ax5], [ax6, ax7]]
            for s, sp in enumerate(spw):
                for pidx, pol in enumerate(pols):
                    # rcmap = [cmaps[pol](float(s) / len(spw))] * len(clvls[pol])
                    rcmap = [plt.cm.RdYlBu(float(s) / len(spw))] * len(clvls[pol])
                    rmap_plt = smap.Map(datas[pol][s, :, :], hdu.header)
                    rmap_plt_ = pmX.Sunmap(rmap_plt)
                    if nspws > 1:
                        rmap_plt_.contourf(axes=[axs[pidx][0], axs[pidx][1]], colors=rcmap,
                                           levels=clvls[pol] * np.nanmax(rmap_plt.data), alpha=calpha)
                    else:
                        rmap_plt_.contour(axes=[axs[pidx][0], axs[pidx][1]], cmap=cmaps[pol],
                                          levels=clvls[pol] * np.nanmax(rmap_plt.data), alpha=calpha)
                    rmap_plt_.draw_limb(axes=[axs[pidx][0], axs[pidx][1]])
                    rmap_plt_.draw_grid(axes=[axs[pidx][0], axs[pidx][1]])
                    if s == 0:
                        if nspws < 2:
                            title = title0 + ' {0} {1:6.3f} GHz'.format(observatory, (bfreqghz + efreqghz) / 2.0)
                        else:
                            title = title0 + ' {0} multi spws'.format(observatory)
                        axs[pidx][0].set_title(title + ' ' + pols[pidx], fontsize=9)
                        rect = mpl.patches.Rectangle((xyrange[0][0], xyrange[1][0]), sz_x.value, sz_y.value,
                                                     edgecolor='w',
                                                     facecolor='none')
                        axs[pidx][0].add_patch(rect)

            ax4.text(0.02, 0.02, 'AIA {0:.0f} '.format(aiamap.wavelength.value) + aiamap.date.strftime('%H:%M:%S'),
                     verticalalignment='bottom',
                     horizontalalignment='left', transform=ax4.transAxes, color='w', fontsize=9)
            ax6.text(0.02, 0.02, 'AIA {0:.0f} '.format(aiamap.wavelength.value) + aiamap.date.strftime('%H:%M:%S'),
                     verticalalignment='bottom',
                     horizontalalignment='left', transform=ax6.transAxes, color='w', fontsize=9)
        else:
            axs = [[ax4, ax5], [ax6, ax7]]
            if nspws < 2:
                title = '{0} {1:6.3f} GHz'.format(observatory, (bfreqghz + efreqghz) / 2.0)
                for pidx, pol in enumerate(pols):
                    rmap_plt = smap.Map(datas[pol][0, :, :], hdu.header)
                    rmap_plt_ = pmX.Sunmap(rmap_plt)
                    rmap_plt_.imshow(axes=[axs[pidx][0], axs[pidx][1]], cmap=cmaps[pol])
                    axs[pidx][0].set_title(title + ' ' + pols[pidx], fontsize=9)
                    rmap_plt_.draw_limb(axes=[axs[pidx][0], axs[pidx][1]])
                    rmap_plt_.draw_grid(axes=[axs[pidx][0], axs[pidx][1]])
                    rect = mpl.patches.Rectangle((xyrange[0][0], xyrange[1][0]), sz_x.value, sz_y.value, edgecolor='w',
                                                 facecolor='none')
                    axs[pidx][0].add_patch(rect)
                    # rmap_plt_.imshow(axes=axs[pidx][1], cmap=cmaps[pol])
                    # rmap_plt_.draw_limb(axes=axs[pidx][1])
                    # rmap_plt_.draw_grid(axes=axs[pidx][1])
            else:
                title = '{0} multi spw'.format(observatory, (bfreqghz + efreqghz) / 2.0)
                for s, sp in enumerate(spw):
                    for pidx, pol in enumerate(pols):
                        rcmap = [cmaps[pol](float(s) / len(spw))] * len(clvls[pol])
                        rmap_plt = smap.Map(datas[pol][s, :, :], hdu.header)
                        rmap_plt_ = pmX.Sunmap(rmap_plt)
                        rmap_plt_.contourf(axes=[axs[pidx][0], axs[pidx][1]], colors=rcmap,
                                           levels=clvls[pol] * np.nanmax(rmap_plt.data), alpha=calpha)
                        axs[pidx][0].set_title(title + ' ' + pols[pidx], fontsize=9)
                        rmap_plt_.draw_limb(axes=[axs[pidx][0], axs[pidx][1]])
                        rmap_plt_.draw_grid(axes=[axs[pidx][0], axs[pidx][1]])
                        if s == 0:
                            rect = mpl.patches.Rectangle((xyrange[0][0], xyrange[1][0]), sz_x.value, sz_y.value,
                                                         edgecolor='w',
                                                         facecolor='none')
                            axs[pidx][0].add_patch(rect)
                        # rmap_plt_.contourf(axes=axs[pidx][1], colors=rcmap,
                        #                    levels=clvls[pol] * np.nanmax(rmap_plt.data), alpha=calpha)
                        # rmap_plt_.draw_limb(axes=axs[pidx][1])
                        # rmap_plt_.draw_grid(axes=axs[pidx][1])

        ax6.set_xlim(-1220, 1220)
        ax6.set_ylim(-1220, 1220)
        ax7.set_xlim(xyrange[0])
        ax7.set_ylim(xyrange[1])
        ax4.set_ylabel('')
        # ax6.set_yticklabels([])
        ax5.set_ylabel('')
        # ax7.set_yticklabels([])
        ax5.text(0.02, 0.02, observatory + ' ' + rmap.date.strftime('%H:%M:%S.%f')[:-3], verticalalignment='bottom',
                 horizontalalignment='left',
                 transform=ax5.transAxes, color='k', fontsize=9)
        ax7.text(0.02, 0.02, observatory + ' ' + rmap.date.strftime('%H:%M:%S.%f')[:-3], verticalalignment='bottom',
                 horizontalalignment='left',
                 transform=ax7.transAxes, color='k', fontsize=9)

        axs = [ax1, ax2, ax3, ax4, ax5, ax6, ax7]
        try:
            axs = axs + [ax3_2]
        except:
            pass
        for ax in axs:
            for tick in ax.get_xticklabels():
                tick.set_fontsize(8)
            for tick in ax.get_yticklabels():
                tick.set_fontsize(8)
            ax.set_xlabel(ax.get_xlabel(), fontsize=9)
            ax.set_ylabel(ax.get_ylabel(), fontsize=9)

        fig.subplots_adjust(top=0.94, bottom=0.07, left=0.06, right=0.94, hspace=0.80, wspace=0.88)

        if nspws >= 2:
            try:
                import matplotlib.colorbar as colorbar
                axs = [ax4, ax7]
                ax1_pos = axs[0].get_position().extents
                ax2_pos = axs[1].get_position().extents
                caxcenter = (ax1_pos[2] + ax2_pos[0]) / 2.0 - ax1_pos[2] + ax2_pos[2]
                caxwidth = (ax2_pos[0] - ax1_pos[2]) / 2.0
                cayheight = ax1_pos[3] - 0.05 - ax2_pos[1]

                bounds = np.linspace(cfreqs[0] - 0.25, cfreqs[-1] + 0.25, len(cfreqs) + 1)
                ticks = cfreqs
                cax = plt.axes((caxcenter - caxwidth / 2.0, ax2_pos[1], caxwidth, cayheight))

                cb = colorbar.ColorbarBase(cax, norm=colors.Normalize(vmax=cfreqs[-1], vmin=cfreqs[0]),
                                           cmap=plt.cm.RdYlBu,
                                           orientation='vertical', boundaries=bounds, spacing='uniform', ticks=ticks,
                                           format='%4.1f', alpha=calpha)
                ax.text(0.5, 1.04, 'MW', ha='center', va='bottom', transform=cax.transAxes, color='k',
                        fontweight='normal')
                ax.text(0.5, 1.01, '[GHz]', ha='center', va='bottom', transform=cax.transAxes, color='k',
                        fontweight='normal')
                cax.xaxis.set_visible(False)
                cax.tick_params(axis="y", direction="in", pad=-20., length=0, colors='k', labelsize=8)
            except:
                pass

        fig.canvas.draw_idle()
        fig.show()
    return outfits
